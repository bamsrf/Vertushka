# Vinyl палитра (из Mobile/lib/vinylColor.ts)

Family-цвета для кноба-винила. `primaryColor` → VinylSpinner сам выводит
bright/dark/edge через saturate/darken. Для рандом-дефолта бери `primary` любой
строки.

| Family | primary | заметка |
|---|---|---|
| red | `#E53935` | crimson `#C62828`, maroon `#880E4F`, scarlet `#D32F2F` |
| blue | `#1E88E5` | cobalt `#1565C0`, navy `#0D47A1`, sapphire `#1A237E`, indigo `#3949AB`, ice `#B3E5FC`, sky `#4FC3F7` |
| green | `#43A047` | emerald `#2E7D32`, lime `#C6FF00`, teal `#00897B`, olive `#827717`, turquoise `#00BCD4`, mint `#A5D6A7`, seafoam `#4DB6AC`, neon `#76FF03` |
| yellow | `#FDD835` | lemon `#FFEE58`, cream `#FFF8E1`, ivory `#FFFFF0`, butter `#FFF9C4`, neon `#F4FF81` |
| orange | `#FB8C00` | amber `#FF8F00`, gold `#FFD600` |
| purple* | `#7E57C2` | (демо translucent) |

Системные:
- navy label disc: `#1C1D3A`
- label text: `#B8BCDB` (Вертушка), `#5C6080` (33⅓ RPM)
- groove grey (дефолт без цвета): `#C8CCD2`
- черная дырка: `#000`

Типы заливки (`type` в VinylColorConfig): `solid` · `translucent` (opacity .85)
· `marble` (secondary-разводы) · `splatter` (secondary-брызги) · `cic`
(другой цвет в центре).

Рекомендация для кноба: дефолт `solid` + рандом family; `splatter`/`marble`
держать как редкий «премиум» вариант.
