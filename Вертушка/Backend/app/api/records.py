"""
API для работы с пластинками
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.record import Record
from app.api.auth import get_current_user, get_current_user_optional
from app.schemas.record import (
    RecordCreate,
    RecordResponse,
    RecordSearchResult,
    RecordSearchResponse,
    CoverScanRequest,
    CoverScanResponse,
    MasterSearchResponse,
    MasterRelease,
    MasterVersionsResponse,
    ReleaseSearchResponse,
    ArtistSearchResponse,
    Artist,
)
from app.services.discogs import DiscogsService
from app.services.openai_vision import OpenAIVisionService, CoverRecognitionError

router = APIRouter()


async def _ensure_record_artist_data(record: Record, db: AsyncSession) -> None:
    """
    Обогащает запись данными артиста (artist_id, artist_thumb_image_url),
    если они отсутствуют в discogs_data. Обновляет запись в БД для кэширования.
    """
    discogs_data = record.discogs_data
    if not discogs_data:
        return

    # Уже есть данные артиста — ничего не делаем
    if discogs_data.get("artist_thumb_image_url"):
        return

    artist_id = discogs_data.get("artist_id")

    # Если artist_id нет — достаём из Discogs по release ID
    if not artist_id and record.discogs_id:
        try:
            discogs = DiscogsService()
            release_raw = await discogs._get(
                f"{discogs.BASE_URL}/releases/{record.discogs_id}"
            )
            artists = release_raw.get("artists", [])
            if artists:
                artist_id = str(artists[0].get("id"))
        except Exception:
            return

    if not artist_id:
        return

    # Получаем миниатюру артиста
    try:
        discogs = DiscogsService()
        artist_thumb = await discogs._get_artist_thumb(artist_id)
        if artist_thumb:
            # Обновляем discogs_data — переприсваиваем для корректного отслеживания SQLAlchemy
            updated_data = {**discogs_data, "artist_id": artist_id, "artist_thumb_image_url": artist_thumb}
            record.discogs_data = updated_data
            await db.commit()
            await db.refresh(record)
    except Exception:
        pass


async def get_or_create_record_by_discogs_id(
    discogs_id: str,
    db: AsyncSession
) -> Record:
    """
    Найти или создать Record по discogs_id.
    Используется в других endpoints для получения Record перед добавлением в коллекцию/вишлист.
    """
    # Проверяем локальную БД
    result = await db.execute(
        select(Record).where(Record.discogs_id == discogs_id)
    )
    record = result.scalar_one_or_none()
    
    if record:
        return record
    
    # Запрос в Discogs
    discogs = DiscogsService()
    
    try:
        record_data = await discogs.get_release(discogs_id)
        
        # Создаём запись в БД
        record = Record(
            discogs_id=record_data.get("id"),
            discogs_master_id=record_data.get("master_id"),
            title=record_data.get("title", "Unknown"),
            artist=record_data.get("artist", "Unknown"),
            label=record_data.get("label"),
            catalog_number=record_data.get("catalog_number"),
            year=record_data.get("year"),
            country=record_data.get("country"),
            genre=record_data.get("genre"),
            style=record_data.get("style"),
            format_type=record_data.get("format"),
            barcode=record_data.get("barcode"),
            cover_image_url=record_data.get("cover_image"),
            thumb_image_url=record_data.get("thumb_image"),
            estimated_price_min=record_data.get("price_min"),
            estimated_price_max=record_data.get("price_max"),
            estimated_price_median=record_data.get("price_median"),
            discogs_data=record_data,
            tracklist=record_data.get("tracklist"),
        )
        
        db.add(record)
        await db.commit()
        await db.refresh(record)
        
        return record
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении данных из Discogs: {str(e)}"
        )


@router.get("/search", response_model=RecordSearchResponse)
async def search_records(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    artist: str | None = Query(None, description="Фильтр по артисту"),
    year: int | None = Query(None, description="Фильтр по году"),
    label: str | None = Query(None, description="Фильтр по лейблу"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск пластинок в Discogs.
    Не требует авторизации, но с авторизацией может сохранять историю.
    """
    discogs = DiscogsService()
    
    try:
        results = await discogs.search(
            query=q,
            artist=artist,
            year=year,
            label=label,
            page=page,
            per_page=per_page
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске в Discogs: {str(e)}"
        )


@router.post("/scan/barcode", response_model=list[RecordSearchResult])
async def scan_barcode(
    barcode: str = Query(..., min_length=8, max_length=20, description="Штрихкод"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск пластинки по штрихкоду.
    Требует авторизации.
    """
    # Сначала проверяем локальную БД
    result = await db.execute(
        select(Record).where(Record.barcode == barcode)
    )
    local_record = result.scalar_one_or_none()
    
    if local_record:
        return [RecordSearchResult(
            discogs_id=local_record.discogs_id or "",
            title=local_record.title,
            artist=local_record.artist,
            label=local_record.label,
            year=local_record.year,
            country=local_record.country,
            cover_image_url=local_record.cover_image_url,
            thumb_image_url=local_record.thumb_image_url,
            format_type=local_record.format_type,
        )]
    
    # Поиск в Discogs
    discogs = DiscogsService()
    
    try:
        results = await discogs.search_by_barcode(barcode)
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске по штрихкоду: {str(e)}"
        )


@router.post("/scan/cover/", response_model=CoverScanResponse)
async def scan_cover(
    request: CoverScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Распознавание обложки пластинки через AI Vision.
    Принимает base64-encoded JPEG, возвращает результаты поиска Discogs.
    Требует авторизации.
    """
    if len(request.image_base64) > 10_000_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Изображение слишком большое (макс. ~7.5 МБ)"
        )

    vision = OpenAIVisionService()
    try:
        recognition = await vision.recognize_cover(request.image_base64)
    except CoverRecognitionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка AI-сервиса: {str(e)}"
        )

    artist = recognition["artist"]
    album = recognition["album"]

    query_parts = []
    if artist:
        query_parts.append(artist)
    if album:
        query_parts.append(album)
    search_query = " ".join(query_parts)

    discogs = DiscogsService()
    try:
        search_response = await discogs.search(
            query=search_query,
            artist=artist if artist else None,
            per_page=10,
        )
        results = search_response.results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске в Discogs: {str(e)}"
        )

    return CoverScanResponse(
        recognized_artist=artist,
        recognized_album=album,
        results=results,
    )


@router.get("/{record_id}", response_model=RecordResponse)
async def get_record(
    record_id: UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о пластинке"""
    result = await db.execute(select(Record).where(Record.id == record_id))
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пластинка не найдена"
        )

    # Обогащаем данные артиста, если отсутствуют
    await _ensure_record_artist_data(record, db)

    return record


@router.get("/discogs/{discogs_id}", response_model=RecordResponse)
async def get_record_by_discogs_id(
    discogs_id: str,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение информации о пластинке по Discogs ID.
    Если пластинка не найдена в локальной БД, запрашивает Discogs и сохраняет.
    """
    # Проверяем локальную БД
    result = await db.execute(
        select(Record).where(Record.discogs_id == discogs_id)
    )
    record = result.scalar_one_or_none()

    if record:
        # Обогащаем данные артиста, если отсутствуют
        await _ensure_record_artist_data(record, db)

        discogs_data = record.discogs_data or {}
        response = RecordResponse.model_validate(record)
        response.artist_id = discogs_data.get("artist_id")
        response.artist_thumb_image_url = discogs_data.get("artist_thumb_image_url")
        return response

    # Запрос в Discogs
    discogs = DiscogsService()

    try:
        record_data = await discogs.get_release(discogs_id)

        # Создаём запись в БД
        record = Record(
            discogs_id=record_data.get("id"),
            discogs_master_id=record_data.get("master_id"),
            title=record_data.get("title", "Unknown"),
            artist=record_data.get("artist", "Unknown"),
            label=record_data.get("label"),
            catalog_number=record_data.get("catalog_number"),
            year=record_data.get("year"),
            country=record_data.get("country"),
            genre=record_data.get("genre"),
            style=record_data.get("style"),
            format_type=record_data.get("format"),
            barcode=record_data.get("barcode"),
            cover_image_url=record_data.get("cover_image"),
            thumb_image_url=record_data.get("thumb_image"),
            estimated_price_min=record_data.get("price_min"),
            estimated_price_max=record_data.get("price_max"),
            estimated_price_median=record_data.get("price_median"),
            discogs_data=record_data,
            tracklist=record_data.get("tracklist"),
        )

        db.add(record)
        await db.commit()
        await db.refresh(record)

        response = RecordResponse.model_validate(record)
        response.artist_id = record_data.get("artist_id")
        response.artist_thumb_image_url = record_data.get("artist_thumb_image_url")
        return response

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении данных из Discogs: {str(e)}"
        )


@router.post("/", response_model=RecordResponse, status_code=status.HTTP_201_CREATED)
async def create_record(
    record_data: RecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Создание пластинки вручную (без Discogs).
    Требует авторизации.
    """
    record = Record(**record_data.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record


@router.get("/masters/search", response_model=MasterSearchResponse)
async def search_masters(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Поиск мастер-релизов в Discogs.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        results = await discogs.search_masters(
            query=q,
            page=page,
            per_page=per_page
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске мастер-релизов: {str(e)}"
        )


@router.get("/releases/search", response_model=ReleaseSearchResponse)
async def search_releases(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    format: str | None = Query(None, description="Фильтр по формату (Vinyl, CD, Cassette)"),
    country: str | None = Query(None, description="Фильтр по стране"),
    year: int | None = Query(None, description="Фильтр по году"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Поиск конкретных релизов с фильтрами в Discogs.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        results = await discogs.search_releases(
            query=q,
            format=format,
            country=country,
            year=year,
            page=page,
            per_page=per_page
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске релизов: {str(e)}"
        )


@router.get("/masters/{master_id}", response_model=MasterRelease)
async def get_master(
    master_id: str,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Получение информации о мастер-релизе.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        master = await discogs.get_master(master_id)
        return master
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении мастер-релиза: {str(e)}"
        )


@router.get("/masters/{master_id}/versions", response_model=MasterVersionsResponse)
async def get_master_versions(
    master_id: str,
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(50, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Получение всех версий (изданий) мастер-релиза.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        versions = await discogs.get_master_versions(
            master_id=master_id,
            page=page,
            per_page=per_page
        )
        return versions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении версий мастер-релиза: {str(e)}"
        )


@router.get("/artists/search", response_model=ArtistSearchResponse)
async def search_artists(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Поиск артистов в Discogs.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        results = await discogs.search_artists(
            query=q,
            page=page,
            per_page=per_page
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при поиске артистов: {str(e)}"
        )


@router.get("/artists/{artist_id}", response_model=Artist)
async def get_artist(
    artist_id: str,
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Получение информации об артисте.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        artist = await discogs.get_artist(artist_id)
        return artist
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении данных артиста: {str(e)}"
        )


@router.get("/artists/{artist_id}/releases", response_model=ReleaseSearchResponse)
async def get_artist_releases(
    artist_id: str,
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(50, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Получение релизов артиста.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        releases = await discogs.get_artist_releases(
            artist_id=artist_id,
            page=page,
            per_page=per_page
        )
        return releases
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении релизов артиста: {str(e)}"
        )


@router.get("/artists/{artist_id}/masters", response_model=MasterSearchResponse)
async def get_artist_masters(
    artist_id: str,
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(50, ge=1, le=100, description="Записей на страницу"),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Получение только master releases артиста (альбомы, синглы, EP).
    Возвращает только основные релизы без всех версий/изданий.
    Не требует авторизации.
    """
    discogs = DiscogsService()

    try:
        masters = await discogs.get_artist_masters(
            artist_id=artist_id,
            page=page,
            per_page=per_page
        )
        return masters
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении master releases артиста: {str(e)}"
        )

