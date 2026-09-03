#!/bin/bash
# ===========================================
# Снимок ресурсов сервера — одна строка в CSV за вызов.
#
# Зачем: по одной точке нельзя отличить «память вышла на плато» от «ползёт
# вверх». Крон зовёт это раз в 5 минут, через сутки в файле 288 точек, и
# вопрос «утечка или нет» закрывается графиком, а не догадкой.
#
# Ставится кроном:  */5 * * * * bash ~/metrics/resource_sample.sh
# Читать:           bash ~/metrics/resource_sample.sh report
# ===========================================
set -u

OUT="$HOME/metrics/resources.csv"
mkdir -p "$HOME/metrics"

# ── Режим отчёта ────────────────────────────────────────────────────────────
# Второй аргумент — путь к другому CSV (для проверки логики на выдуманных
# данных, не трогая боевую историю).
if [ "${1:-}" = "report" ]; then
    SRC="${2:-$OUT}"
    [ -f "$SRC" ] || { echo "Замеров ещё нет: $SRC"; exit 1; }
    awk -F, '
function epoch(s,   t) { t = s; gsub(/[-:]/, " ", t); return mktime(t " 00") }
function hrs(a, b) { return (b - a) / 3600.0 }
function hhmm(x) { return strftime("%d.%m %H:%M", x) }

NR == 1 { next }
NF < 14 { next }
{
    n++
    ts[n] = $1; ep[n] = epoch($1)
    cpu[n] = $2 + $3
    mem[n] = $6 + 0; swap[n] = $8 + 0
    api[n] = $9 + 0; db[n] = $10 + 0; conns[n] = $14 + 0
}
END {
    if (n < 2) { printf "Точек пока %d — отчёт будет осмысленным после нескольких часов.\n", n; exit }

    printf "Точек: %d   с %s по %s   (%.1f ч)\n", n, ts[1], ts[n], hrs(ep[1], ep[n])

    # ── Резка истории по рестартам api ──────────────────────────────────────
    # Деплой пересоздаёт контейнер, и RSS падает с ~700 МБ до ~135. Считать
    # рост «первая точка → последняя» через такой обрыв бессмысленно: получится
    # отрицательная скорость там, где память на самом деле росла.
    # Порог двойной (и −100 МБ, и падение на треть), чтобы обычные колебания
    # рабочего набора не резали историю на куски.
    s = 1; from[1] = 1
    for (i = 2; i <= n; i++)
        if (api[i-1] > 0 && api[i] < api[i-1] - 100 && api[i] < api[i-1] * 0.7) {
            to[s] = i - 1; s++; from[s] = i
        }
    to[s] = n

    printf "\n── ПАМЯТЬ API ПО УЧАСТКАМ МЕЖДУ РЕСТАРТАМИ ──────────────────────────\n"
    printf "%-26s %7s %9s %9s %12s\n", "участок", "длит.", "старт", "конец", "скорость"
    best = 0; bestlen = 0
    for (k = 1; k <= s; k++) {
        a = from[k]; b = to[k]
        h = hrs(ep[a], ep[b])
        if (b - a < 2 || h < 0.5) {
            printf "%-26s %6.1fч %8dМБ %8dМБ %12s\n", \
                   hhmm(ep[a]) " → " hhmm(ep[b]), h, api[a], api[b], "коротко"
            continue
        }
        rate = (api[b] - api[a]) / h
        printf "%-26s %6.1fч %8dМБ %8dМБ %+8.1f МБ/ч\n", \
               hhmm(ep[a]) " → " hhmm(ep[b]), h, api[a], api[b], rate
        if (h > bestlen) { bestlen = h; best = k; bestrate = rate; bestend = api[b] }
    }

    # ── Вывод по самому длинному участку ────────────────────────────────────
    LIMIT = 1000   # mem_limit контейнера api, МБ
    printf "\n"
    if (best == 0)
        print "Вывод: сплошного участка нужной длины пока нет — нужны часы без деплоя."
    else if (bestrate > 5) {
        printf "Вывод: рост устойчивый, %+.1f МБ/ч — плато НЕ достигнуто.\n", bestrate
        left = (LIMIT - bestend) / bestrate
        if (left > 0)
            printf "        При лимите %d МБ упор примерно через %.0f ч непрерывной работы.\n", LIMIT, left
    }
    else if (bestrate < -5)
        printf "Вывод: память убывает (%+.1f МБ/ч) — вероятно, отдаёт кэш.\n", bestrate
    else
        printf "Вывод: плато, %+.1f МБ/ч. Это не утечка — рабочий набор просто устоялся.\n", bestrate

    # ── То, что рестарт не сбрасывает ───────────────────────────────────────
    printf "\n── ЧТО НЕ СБРАСЫВАЕТСЯ РЕСТАРТОМ ────────────────────────────────────\n"
    printf "%-16s %8s %8s %9s\n", "метрика", "первая", "последняя", "дельта"
    printf "%-16s %8d %8d %+9d\n", "db_mb",        db[1],    db[n],    db[n]    - db[1]
    printf "%-16s %8d %8d %+9d\n", "mem_used_mb",  mem[1],   mem[n],   mem[n]   - mem[1]
    printf "%-16s %8d %8d %+9d\n", "swap_used_mb", swap[1],  swap[n],  swap[n]  - swap[1]
    printf "%-16s %8d %8d %+9d\n", "pg_conns",     conns[1], conns[n], conns[n] - conns[1]

    # ── CPU: день против ночи ───────────────────────────────────────────────
    # Ради этого замер и ставился: панель Beget рисует ~125%, живой замер днём
    # даёт 4%. Если нагрузка ночная — она проявится именно здесь.
    peak = -1
    for (i = 1; i <= n; i++) {
        sum += cpu[i]
        if (cpu[i] > peak) { peak = cpu[i]; peakat = ts[i] }
        h24 = strftime("%H", ep[i]) + 0
        if (h24 >= 0 && h24 < 7) { nsum += cpu[i]; ncnt++ } else { dsum += cpu[i]; dcnt++ }
    }
    printf "\n── CPU (%% от 2 ядер) ────────────────────────────────────────────────\n"
    printf "среднее %.1f%%   пик %d%% в %s\n", sum / n, peak, peakat
    if (ncnt) printf "ночь 00-07: %.1f%% (точек: %d)   ", nsum / ncnt, ncnt
    else      printf "ночь 00-07: точек пока нет   "
    if (dcnt) printf "день 07-24: %.1f%% (точек: %d)\n", dsum / dcnt, dcnt
    else      printf "день 07-24: точек пока нет\n"
}
' "$SRC"
    exit 0
fi

# ── CPU: дельта по /proc/stat за 5 секунд ───────────────────────────────────
# Мгновенный top врёт (сам себя и застаёт), поэтому считаем интервалом.
read -r _ u1 n1 s1 i1 w1 _ < /proc/stat; t1=$((u1+n1+s1+i1+w1))
sleep 5
read -r _ u2 n2 s2 i2 w2 _ < /proc/stat; t2=$((u2+n2+s2+i2+w2))
dt=$((t2-t1)); [ "$dt" -gt 0 ] || dt=1
cpu_user=$(( (u2-u1+n2-n1)*100/dt ))
cpu_sys=$(( (s2-s1)*100/dt ))
cpu_io=$(( (w2-w1)*100/dt ))

load1=$(cut -d' ' -f1 /proc/loadavg)

# ── Память хоста ────────────────────────────────────────────────────────────
mem_used=$(free -m | awk '/^Mem:/{print $3}')
mem_avail=$(free -m | awk '/^Mem:/{print $7}')
swap_used=$(free -m | awk '/^Swap:/{print $3}')

# ── Память контейнеров ──────────────────────────────────────────────────────
# docker stats печатает «671.7MiB» или «1.018GiB» — приводим всё к МБ.
# api ловим по префиксу: blue-green меняет цвет активного контейнера.
stats=$(docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null)
mb() {
    echo "$stats" | awk -v pat="$1" '
        $0 ~ pat {
            v=$2
            sub(/\/.*/,"",v)
            if (v ~ /GiB/)      { sub(/GiB/,"",v); s+=v*1024 }
            else if (v ~ /MiB/) { sub(/MiB/,"",v); s+=v }
            else if (v ~ /KiB/) { sub(/KiB/,"",v); s+=v/1024 }
        }
        END { printf "%.0f", s }'
}
api=$(mb '^vertushka_api_')
db=$(mb '^vertushka_db ')
sched=$(mb '^vertushka_scheduler ')
redis=$(mb '^vertushka_redis ')
glitch=$(mb '^glitchtip-')

# ── Postgres: сколько коннектов висит ───────────────────────────────────────
conns=$(docker exec vertushka_db psql -U vertushka_user -d vertushka -tAc \
    "select count(*) from pg_stat_activity where backend_type='client backend'" 2>/dev/null | tr -d ' ')
[ -n "$conns" ] || conns=0

[ -f "$OUT" ] || echo "ts,cpu_user,cpu_sys,cpu_iowait,load1,mem_used_mb,mem_avail_mb,swap_used_mb,api_mb,db_mb,sched_mb,redis_mb,glitchtip_mb,pg_conns" > "$OUT"
echo "$(date '+%Y-%m-%d %H:%M'),$cpu_user,$cpu_sys,$cpu_io,$load1,$mem_used,$mem_avail,$swap_used,$api,$db,$sched,$redis,$glitch,$conns" >> "$OUT"
