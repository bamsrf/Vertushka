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

# ── Режим отчёта: первая/последняя точка и дельта по каждой колонке ──────────
if [ "${1:-}" = "report" ]; then
    [ -f "$OUT" ] || { echo "Замеров ещё нет: $OUT"; exit 1; }
    awk -F, 'NR==1{for(i=1;i<=NF;i++) h[i]=$i; n=NF; next}
             NR==2{for(i=1;i<=n;i++) f[i]=$i; first=$1}
             {for(i=1;i<=n;i++) l[i]=$i; last=$1; cnt++}
             END{
               if(cnt==0){print "Только заголовок, данных нет."; exit}
               printf "Точек: %d   с %s по %s\n\n", cnt, first, last
               printf "%-16s %10s %10s %10s\n", "метрика", "первая", "последняя", "дельта"
               for(i=2;i<=n;i++){
                 d=l[i]-f[i]
                 printf "%-16s %10s %10s %+10.1f\n", h[i], f[i], l[i], d
               }
             }' "$OUT"
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
