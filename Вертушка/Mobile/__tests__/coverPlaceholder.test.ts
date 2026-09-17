/**
 * Быстрый первый кадр героя: наша ступень 640 вместо 150px-thumb'а Discogs.
 *
 * 17.09.2026, жалоба владельца: «заходишь в релиз — пластинка всё время
 * пикселится и потом прогружается». Прогрессивная загрузка тут задумана, но
 * первым кадром шёл `thumb_image_url` — 150 px с i.discogs.com. Апскейл в 7.8
 * раза на полноэкранного героя это и есть та каша, а чужой хост из РФ отвечает
 * медленно, так что каша ещё и висела. Плитка списка к этому моменту уже
 * скачала нашу ступень 640 — берём её: тот же URL, попадание в disk-кэш.
 */
import {
  getFastPlaceholderUrl,
  getPlaceholderCoverUrl,
  PLACEHOLDER_COVER_PX,
  recordPreviewParams,
} from '../lib/api';

const ORIGIN = 'https://api.vinyl-vertushka.ru';
const V = '?v=1789417292';
const DISCOGS_150 =
  'https://i.discogs.com/abc/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz.jpeg';
const DISCOGS_600 =
  'https://i.discogs.com/abc/rs:fit/g:sm/q:90/h:600/w:600/czM6Ly9kaXNjb2dz.jpeg';

describe('getFastPlaceholderUrl', () => {
  it('режет наше зеркало до ступени и сохраняет метку версии', () => {
    const url = getFastPlaceholderUrl({
      cover_url: `${ORIGIN}/covers/2115210.jpg${V}`,
      thumb_image_url: DISCOGS_150,
    });
    expect(url).toBe(`${ORIGIN}/covers/w/${PLACEHOLDER_COVER_PX}/2115210.jpg${V}`);
  });

  it('метка не обязательна — незазеркаленный мост тоже режется', () => {
    const url = getFastPlaceholderUrl({ cover_url: `${ORIGIN}/covers/777.jpg` });
    expect(url).toBe(`${ORIGIN}/covers/w/${PLACEHOLDER_COVER_PX}/777.jpg`);
  });

  it('внешний мастер нарезать нечем — откат на прежний thumb', () => {
    const rec = { cover_image_url: DISCOGS_600, thumb_image_url: DISCOGS_150 };
    expect(getFastPlaceholderUrl(rec)).toBe(getPlaceholderCoverUrl(rec));
    expect(getFastPlaceholderUrl(rec)).toBe(DISCOGS_150);
  });

  it('мастера нет вовсе — прежнее поведение', () => {
    expect(getFastPlaceholderUrl({ thumb_image_url: DISCOGS_150 })).toBe(DISCOGS_150);
    expect(getFastPlaceholderUrl(null)).toBeUndefined();
    expect(getFastPlaceholderUrl({})).toBeUndefined();
  });

  it('ступень совпадает с той, что просит плитка Маркета', () => {
    // Ячейка Маркета = 0.48 ширины экрана. На всех реальных сочетаниях ширины
    // и DPR она округляется вверх ровно в 640 — значит плейсхолдер придёт из
    // disk-кэша, а не из сети. Ради этого ступень и зафиксирована.
    for (const width of [375, 393, 430]) {
      for (const dpr of [2, 3]) {
        const slot = Math.ceil(width * 0.48 * dpr);
        expect(slot).toBeGreaterThan(320);
        expect(slot).toBeLessThanOrEqual(PLACEHOLDER_COVER_PX);
      }
    }
    // Сетка коллекции на широком экране (430pt @3x → 645) выходит за
    // последнюю ступень: sizedCoverUrl отдаёт там сам мастер. Попадания в
    // кэш плейсхолдером не будет — но не будет и пикселей, мастер уже скачан
    // и герой отрисуется им сразу. Фиксируем как известное поведение.
    expect(Math.ceil((430 / 2) * 3)).toBeGreaterThan(PLACEHOLDER_COVER_PX);
  });
});

describe('recordPreviewParams', () => {
  it('previewThumb уходит нашей нарезкой, а не чужим 150px', () => {
    const params = recordPreviewParams({
      title: 'T',
      cover_url: `${ORIGIN}/covers/2115210.jpg${V}`,
      thumb_image_url: DISCOGS_150,
    });
    expect(params.previewThumb).toBe(
      `${ORIGIN}/covers/w/${PLACEHOLDER_COVER_PX}/2115210.jpg${V}`
    );
  });
});
