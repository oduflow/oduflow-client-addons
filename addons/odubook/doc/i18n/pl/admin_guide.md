<!-- i18n source=admin_guide.md sha=a626ae271248 lang=pl -->
# Administracja księgą dokumentacji

Księga jest oparta na plikach. Podręczniki modułów i archiwum zmian nie
przechowują dokumentacji w bazie danych i nie są tłumaczone w czasie obsługi
żądania. W bazie znajdują się tylko osobiste oznaczenia przeczytania archiwum
zmian oraz dokumenty położone ręcznie na półce **Podręczniki**.

## Kontrola dostępu

Podręcznik użytkownika, Podręczniki i Zmiany są dostępne dla użytkowników
wewnętrznych. Podręcznik administratora jest ograniczony do grupy Ustawienia
(`base.group_system`) zarówno w menu, jak i w punkcie końcowym serwera. Na półce
Podręczników użytkownicy wewnętrzni mają wyłącznie prawo odczytu; dodawanie i
usuwanie dokumentów wymaga grupy Ustawienia, czego pilnuje ACL, a nie ukrywanie
przycisków.

Oznaczenia przeczytania są przechowywane w `odubook.change.read` (jeden wiersz
na użytkownika, moduł i datę). Użytkownicy wewnętrzni mogą je odczytywać,
tworzyć i zmieniać, ale nigdy usuwać, a reguła rekordu ogranicza każdą operację
do ich własnych wierszy.

## Nieprzeczytane wpisy

Wpis to jeden moduł z jednej daty. Zostaje oznaczony jako przeczytany, gdy tylko
jego treść trafi do czytelnika; **Oznacz wszystkie jako przeczytane** oznacza
wszystko, co obecnie znajduje się na dysku.

Dwa progi są stałymi w `models/odubook.py`:

| Stała | Domyślnie | Znaczenie |
|---|---|---|
| `NEW_ENTRY_DAYS` | 3 | jak długo wpis ma zieloną etykietę **Nowe** |
| `UNREAD_HORIZON_DAYS` | 90 | starsze wpisy nigdy nie liczą się jako nieprzeczytane |

Horyzont sprawia, że uzupełnione archiwum historyczne nie zamienia każdej listy
w pogrubiony tekst, i działa tak samo dla nowych pracowników, bez migracji
danych. Usunięcie oznaczeń (na przykład aby ponownie pokazać archiwum jednemu
użytkownikowi) to zwykłe usunięcie wierszy `odubook.change.read`.

## Półka „Podręczniki”

**Podręczniki** przechowują dokumenty, które nie leżą obok kodu modułu. Jeden
rekord `odubook.manual` to jeden dokument: `name` jest tytułem na pasku
bocznym, a `sequence` porządkuje półkę. Pliki żyją w `odubook.manual.file` — po
jednym wierszu na język, każdy z własnym `file_name`.

Dokument dodaje się przyciskiem **Dodaj dokument** pod półką: wybierz plik,
popraw zaproponowany tytuł, wskaż język i potwierdź. Przerywany przycisk języka
nad otwartym dokumentem wgrywa brakujące tłumaczenie; ponowne wgranie tego
samego języka zastępuje plik, a nie dodaje drugiego.

Po włączeniu danych demonstracyjnych moduł dodaje przykładowy dokument: **Sales Cube — sales management model** —
interaktywny artefakt modelu `veles_sales_cube` po angielsku, polsku i rosyjsku.
Powstaje raz przy instalacji z `noupdate="1"`, więc edycja albo usunięcie w UI
przetrwają aktualizację; nowa wersja artefaktu wgrywana jest na półkę ręcznie.

Czytelnik dostaje wersję własnego języka, potem angielską, potem jedyną na
półce — dzięki temu dokument wgrany w jednym języku pozostaje czytelny dla
wszystkich. **Usuń** zdejmuje otwarte tłumaczenie, a ostatnie zabiera ze sobą
cały dokument.

O sposobie wyświetlenia decyduje rozszerzenie pliku, a nie typ MIME przysłany
przez przeglądarkę:

| Rozszerzenie | Wyświetlane jako |
|---|---|
| `md`, `markdown` | wyrenderowany Markdown, jak podręcznik |
| `txt`, `log`, `csv` | zabezpieczony zwykły tekst |
| `html`, `htm` | sam dokument, w piaskownicy ramki |
| `pdf` | przeglądarka PDF |
| `png`, `jpg`, `jpeg`, `gif`, `svg`, `webp`, `bmp` | obraz |
| wszystko inne | wyłącznie odnośnik do pobrania |

Wgrany dokument HTML jest serwowany z `Content-Security-Policy: sandbox` i
wyświetlany w `iframe` bez `allow-same-origin`, więc jego skrypty działają we
własnym origin i nie sięgają sesji Odoo czytelnika. Mimo to półka jest celowo
zapisywalna dla administratora: traktuj wgrany artefakt jak kod, za który
ręczysz.

Plik nie może przekroczyć 25 MB, a po stronie serwera renderowany jest tylko
dokument tekstowy poniżej 4 MB; większy albo nie-UTF-8 plik tekstowy wraca do
odnośnika pobierania.

## Dodawanie dokumentacji do modułu

Moduł dołącza do Księgi przez dodanie plików w katalogu `doc/`:

| Plik | Przeznaczenie |
|---|---|
| `user_guide.md` | Instrukcje dla użytkowników biznesowych |
| `admin_guide.md` | Ustawienia i operacje uprzywilejowane |
| `tech_spec.md` | Kontrakt techniczny; niewidoczny w Księdze |
| `changes/YYYY-MM-DD.md` | Zmiany z jednego dnia, napisane w języku źródłowym |

Wyświetlane są tylko zainstalowane moduły. Prefiks nazwy technicznej nie jest
wymagany.

## Języki dokumentacji

Językiem źródłowym jest angielski. Skonfigurowane języki docelowe to polski
i rosyjski. Kopie podręczników znajdują się w
`doc/i18n/<lang>/user_guide.md` oraz `doc/i18n/<lang>/admin_guide.md`, a wpisy
dziennika zmian są kopiowane plik po pliku do
`doc/i18n/<lang>/changes/YYYY-MM-DD.md`.

Przewodniki i każdy wpis dziennika zmian są utrzymywane we wszystkich trzech
językach: angielskim, polskim i rosyjskim.

Każda kopia zaczyna się znacznikiem SHA wskazującym dokładną wersję źródła,
z której wykonano tłumaczenie. Tłumaczenia należy utrzymywać za pomocą skillu
`odubook-i18n` i sprawdzać poleceniem:

```bash
python3 .claude/skills/odubook-i18n/scripts/check_docs.py
```

W czasie działania pobierany jest krótki kod języka użytkownika Odoo (`pl_PL` →
`pl`), a brakujący dokument wraca do angielskiego źródła — tak samo podręcznik,
jak i wpis dziennika zmian. O tym, jakie daty istnieją w archiwum, zawsze
decydują angielskie źródła, więc brakująca lub nadmiarowa kopia nie może dodać
ani ukryć wpisu. `tech_spec.md` pozostaje wyłącznie w języku źródłowym.

Przyciski języków, które czytelnik widzi nad podręcznikiem lub wpisem dziennika
zmian, nie są nigdzie konfigurowane: to kopie znalezione na dysku. Język
pojawia się, gdy tylko jeden zainstalowany moduł zawiera `doc/i18n/<lang>/`
z tym dokumentem, i znika wraz z ostatnią taką kopią; angielski jest oferowany
zawsze. Zestawy przycisków mogą więc różnić się między sekcjami, jeśli różnią
się ich skonfigurowane kopie, a język zażądany z pominięciem interfejsu serwer
ignoruje. Aby przycisk się pojawił, wystarczy dodać język docelowy do
`LANG.local.md` i przetłumaczyć skonfigurowane dokumenty; żaden rekord
konfiguracyjny nie jest potrzebny.

Czytanie w innym języku niczego nie zapisuje: wybór żyje wyłącznie w otwartym
widoku.

## Pozycja „Język” w menu użytkownika

**Język** — między **Skrótami** a **Moim profilem** pod nazwiskiem samego
użytkownika — zmienia język całego interfejsu. To przeciwieństwo przycisków
Księgi: zapisuje `lang` we własnym rekordzie `res.users` czytelnika i
przeładowuje stronę, ponieważ zbudowany już klient webowy nie potrafi sam
podmienić swoich tłumaczeń.

Z pozycji może korzystać każdy użytkownik bez dodatkowych uprawnień: `lang` to
jedno z pól Odoo, które użytkownik może zapisać sobie sam, a okno nie zapisuje
ani innych pól, ani cudzych rekordów. Żadna grupa jej nie strzeże i nie ma tu
czego konfigurować.

Okno wymienia **aktywne** rekordy `res.lang`, więc język pojawia się w nim
dopiero po instalacji przez **Ustawienia → Tłumaczenia → Języki**. Sama
instalacja języka nie tłumaczy modułów niestandardowych — moduł jest na niego
przetłumaczony tylko wtedy, gdy zawiera `i18n/<lang>.po`. Przyciski języków
samej Księgi są od tego wszystkiego niezależne: czytają kopie Markdown z dysku i
działają dla języka w ogóle niezainstalowanego w bazie.

## Izolowanie błędów

Nieczytelne, nieprawidłowo zakodowane w UTF-8 lub zbyt duże pliki dokumentacji
są pomijane i zapisywane w logu bez przerywania działania całej Księgi.
Wyrenderowany HTML jest buforowany dla każdego workera i odświeżany po zmianie
czasu modyfikacji pliku.

## Raporty z audytu modułów

Otwórz **Księga → Audyt**, aby przeczytać `doc/module-audit.md` z zainstalowanych
modułów. Tylko członkowie `base.group_system` mogą czytać raporty, również przez
bezpośrednie wywołania RPC i eksport PDF. Moduły bez raportu są pomijane; jeśli
żaden zainstalowany moduł nie ma raportu, sekcja jest pusta. Raporty są technicznymi
dokumentami źródłowymi w języku angielskim; tłumaczenia są ignorowane.

Użyj `$audit-modules` ze skilem repozytorium w
`.agents/skills/audit-modules/SKILL.md`, aby przeprowadzić audyt wszystkich modułów
w `addons/` i zapisać raport w każdym module. Obejmuje to moduły niezainstalowane
w bieżącej bazie; ich raporty pojawią się po instalacji. Skil zapisuje dowody,
wagę problemów, zakres i pominięte kontrole. Nie naprawia automatycznie problemów
ani nie zmienia usług. Raporty opisują stan z chwili audytu, a nie bieżący stan usług.

Przeglądarka obsługuje wyszukiwanie tytułów, odnośniki do sekcji oraz pojedynczy
i łączony eksport PDF. Wybór sekcji audytu jest zapisywany oddzielnie od wyboru
w podręcznikach. Odśwież widok po aktualizacji raportów. Zaktualizuj `odubook`
po wdrożeniu tej funkcji, aby zarejestrować menu i załadować zasoby interfejsu.
