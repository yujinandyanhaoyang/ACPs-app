# Book Retrieval Dataset Stats

- Dataset root: `/root/WORK/DATA`
- Goodreads source: `/root/WORK/DATA/raw/goodreads/books.csv`
- Amazon sources: `/root/WORK/DATA/raw/amazon_books/meta_Books.json.gz`, `/root/WORK/DATA/raw/amazon_books/meta_Kindle_Store.json.gz`
- Match heuristic: normalized `title + author/brand`

## 1. 总书目数量

- Goodreads 书目数: **10,000**
- Amazon 书目数: **3,426,619**
- 合计扫描记录数: **3,436,619**

## 2. 各字段填充率

### Goodreads (`books.csv`)

| 字段 | 填充数 | 填充率 |
|---|---:|---:|
| book_id | 10,000 | 100.00% |
| title | 10,000 | 100.00% |
| author | 10,000 | 100.00% |
| rating | 10,000 | 100.00% |
| description / blurb / summary | 0 | 0.00% |
| genres / categories / tags | 0 | 0.00% |

### Amazon (`meta_*.json.gz`)

| 字段 | 填充数 | 填充率 |
|---|---:|---:|
| book_id | 3,426,619 | 100.00% |
| title | 3,423,031 | 99.90% |
| author | 3,323,794 | 97.00% |
| description | 1,714,743 | 50.04% |
| genres | 3,037,190 | 88.64% |
| rating | 0 | 0.00% |

## 3. Description 平均长度

- 非空 description 平均字符长度: **1103.09**
- 有效 description 平均字符长度（>=50 字符）: **1211.44**
- 有效 description 数量（>=50 字符）: **1,558,334**

## 4. Goodreads vs Amazon 交叉匹配率

- 口径：按归一化后的 `title + author/brand` 做近似匹配，因为原始两套源数据并没有统一全局 `book_id`。
- Goodreads 中可在 Amazon 找到匹配的比例: **3.32%**
- Amazon 中可在 Goodreads 找到匹配的比例: **0.01%**
- 命中记录数: **332**

## 5. 样本

### 字段最完整的 5 条

| source | book_id | title | author | completeness | valid_description |
|---|---|---|---|---:|---:|
| amazon | B01HFNYNF2 | Doctor Who Magazine, No. 500 | Tom Spilsbury | 5 | yes |
| amazon | B01HIL55SA | IDRIS ELBA 2017 UK WALL CALENDAR BRAND NEW &amp; FACTORY SEALED BY RED STAR | RED STAR | 5 | yes |
| amazon | B01HILBJ6M | CHRIS HEMSWORTH 2017 UK WALL CALENDAR BRAND NEW &amp; FACTORY SEALED BY RED STAR | RED STAR | 5 | yes |
| amazon | B01HILNAGY | TOM HIDDLESTON 2017 UK WALL CALENDAR BRAND NEW &amp; FACTORY SEALED BY RED STAR | RED STAR | 5 | yes |
| amazon | B01HIUH2AK | Busoni : Konzertstuck fur Klavier mit Orchester | Ferruccio Busoni | 5 | yes |

```json
{"source": "amazon", "book_id": "B01HFNYNF2", "title": "Doctor Who Magazine, No. 500", "author": "Tom Spilsbury", "description": ["Full color magazine about the oldest and most popular science fiction TV show in the world. Celebrating 500 issues with a special assortment of two 116 magazines, a double sided poster, stickers, art card and more."], "genres": ["Books", "Science Fiction & Fantasy"], "rating": "", "completeness": 5, "valid_description": true}
{"source": "amazon", "book_id": "B01HIL55SA", "title": "IDRIS ELBA 2017 UK WALL CALENDAR BRAND NEW &amp; FACTORY SEALED BY RED STAR", "author": "RED STAR", "description": ["SUPERB 16.5 INCH BY 11.5 INCH (297mm by 420mm) (A3 SIZE) NEW 12 MONTH 2017 WALL CALENDAR , PRINTED ON HIGH QUALITY PAPER AND FINISHED TO A HIGH STANDARD, RING BOUND WITH HANGING HOOK AND SEALED WITH AN INTERNAL BOARD STIFFENER, SO WOULD MAKE AN IDEAL GIFT ,12 DIFFERENT FULL SIZE PICTURES ONE FOR EACH MONTH OF THE YEAR"], "genres": ["Books", "Calendars"], "rating": "", "completeness": 5, "valid_description": true}
{"source": "amazon", "book_id": "B01HILBJ6M", "title": "CHRIS HEMSWORTH 2017 UK WALL CALENDAR BRAND NEW &amp; FACTORY SEALED BY RED STAR", "author": "RED STAR", "description": ["SUPERB 16.5 INCH BY 11.5 INCH (297mm by 420mm) (A3 SIZE) NEW 12 MONTH 2017 WALL CALENDAR , PRINTED ON HIGH QUALITY PAPER AND FINISHED TO A HIGH STANDARD, RING BOUND WITH HANGING HOOK AND SEALED WITH AN INTERNAL BOARD STIFFENER, SO WOULD MAKE AN IDEAL GIFT ,12 DIFFERENT FULL SIZE PICTURES ONE FOR EACH MONTH OF THE YEAR"], "genres": ["Books", "Calendars"], "rating": "", "completeness": 5, "valid_description": true}
{"source": "amazon", "book_id": "B01HILNAGY", "title": "TOM HIDDLESTON 2017 UK WALL CALENDAR BRAND NEW &amp; FACTORY SEALED BY RED STAR", "author": "RED STAR", "description": ["SUPERB 16.5 INCH BY 11.5 INCH (297mm by 420mm) (A3 SIZE) NEW 12 MONTH 2017 WALL CALENDAR , PRINTED ON HIGH QUALITY PAPER AND FINISHED TO A HIGH STANDARD, RING BOUND WITH HANGING HOOK AND SEALED WITH AN INTERNAL BOARD STIFFENER, SO WOULD MAKE AN IDEAL GIFT ,12 DIFFERENT FULL SIZE PICTURES ONE FOR EACH MONTH OF THE YEAR"], "genres": ["Books", "Calendars"], "rating": "", "completeness": 5, "valid_description": true}
{"source": "amazon", "book_id": "B01HIUH2AK", "title": "Busoni : Konzertstuck fur Klavier mit Orchester", "author": "Ferruccio Busoni", "description": ["Busoni, Ferruccio : Konzertstck fr Klavier mit Orchester. Op. 31a. Fr zwei Klaviere zu vier Hnden. (2. Klavier an Stelle des Orchesters). Piano Music - 2-Piano Scores This is an Eastman Scores Publishing professional reprint of the work originally published by: Breitkopf & Hartel, Leipzig, 1892, 2 scores, 38 pp. Sheet Music Eastman Scores Publishing Library Commerce ISMN : 979-0-087-00129-8"], "genres": ["Books", "Arts & Photography", "Music"], "rating": "", "completeness": 5, "valid_description": true}
```

### 字段最少的 5 条

| source | book_id | title | author | completeness | valid_description |
|---|---|---|---|---:|---:|
| amazon | B000Y14ASS |  |  | 1 | no |
| amazon | B000Y7525C |  |  | 1 | no |
| amazon | B0012Z3EBE |  |  | 1 | no |
| amazon | B00292ASYK |  |  | 1 | no |
| amazon | B017GTXXB0 |  |  | 1 | no |

```json
{"source": "amazon", "book_id": "B000Y14ASS", "title": "", "author": "", "description": "", "genres": [], "rating": "", "completeness": 1, "valid_description": false}
{"source": "amazon", "book_id": "B000Y7525C", "title": "", "author": "", "description": "", "genres": [], "rating": "", "completeness": 1, "valid_description": false}
{"source": "amazon", "book_id": "B0012Z3EBE", "title": "", "author": "", "description": "", "genres": [], "rating": "", "completeness": 1, "valid_description": false}
{"source": "amazon", "book_id": "B00292ASYK", "title": "", "author": "", "description": "", "genres": [], "rating": "", "completeness": 1, "valid_description": false}
{"source": "amazon", "book_id": "B017GTXXB0", "title": "", "author": "", "description": "", "genres": [], "rating": "", "completeness": 1, "valid_description": false}
```
