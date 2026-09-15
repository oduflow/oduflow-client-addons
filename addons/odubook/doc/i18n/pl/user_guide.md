<!-- i18n source=user_guide.md sha=f6fab75496b1 lang=pl -->
# Księga dokumentacji

Aplikacja **Odubook** gromadzi w jednym miejscu dokumentację zainstalowanych
modułów Odoo. Odczytuje dokumentację przechowywaną razem z kodem modułu, dlatego
instrukcje odpowiadają wdrożonej wersji funkcji.

## Dostępne sekcje

- **Podręcznik użytkownika** zawiera instrukcje codziennej pracy.
- **Podręczniki** to półka dokumentów dodanych ręcznie: plików, które nie leżą
  obok kodu modułu — artefaktów projektowych, umów, zeskanowanych instrukcji.
- **Podręcznik administratora** zawiera ustawienia i operacje uprzywilejowane.
  Jest widoczny tylko dla administratorów Ustawień.
- **Zmiany** pokazują historię aktualizacji dokumentacji: jako strumień
  chronologiczny, według modułu i daty albo według modułów.

## Czytanie dokumentacji

Otwórz **Odubook → Podręcznik użytkownika** i wybierz moduł po lewej stronie.
Użyj pola wyszukiwania, aby filtrować moduły według tytułu. Wybrany podręcznik
pojawi się po prawej stronie i może zawierać nagłówki, listy, tabele, odnośniki,
obrazy oraz przykłady kodu.

Księga wyświetla podręcznik w **Języku Księgi** wybranym w **Preferencjach**
Odoo. Pozostaw to ustawienie puste, aby używać języka interfejsu. Jeżeli
tłumaczenie nie jest dostępne, Księga użyje angielskiej wersji źródłowej danego
podręcznika.

## Zabierz podręcznik ze sobą

Obok każdego nagłówka podręcznika — łącznie z jego tytułem — znajdują się pole
wyboru i dwa przyciski, które pojawiają się po najechaniu kursorem. Działają tak samo w
**Podręczniku użytkownika** i w **Podręczniku administratora**:

- przycisk PDF pobiera to, co znajduje się pod tym nagłówkiem: cały podręcznik,
  gdy naciśniesz go obok tytułu, albo pojedynczą sekcję wraz ze wszystkimi jej
  podsekcjami. Dokument pobierany jest w języku, w którym czytasz.
  Ogrodzone bloki kodu pozostają kompletne, nawet gdy pokazują inny znacznik
  Markdown z nazwą języka.
- pole wyboru dodaje ten nagłówek do zestawu, dzięki czemu kilka rozdziałów
  opuszcza Księgę jako jeden PDF. Opisuje to następna sekcja.
- przycisk odnośnika kopiuje odnośnik do tego nagłówka do schowka. Otwarcie go
  w innym miejscu ponownie otwiera Księgę na tym samym podręczniku, w tym samym
  języku i przewiniętą do tego samego nagłówka. Gdy przeglądarka odmawia
  dostępu do schowka — przez zwykłe HTTP odmawia zawsze — odnośnik zostaje
  pokazany, aby skopiować go ręcznie.

## Zbieranie kilku rozdziałów w jeden PDF

Przycisk PDF eksportuje jeden nagłówek naraz. Gdy potrzebujesz broszury z kilku
rozdziałów — z jednego podręcznika albo z różnych — zaznacz pole wyboru obok
każdego potrzebnego nagłówka. Zaznaczony nagłówek zachowuje widoczne pole
wyboru, więc zawsze widzisz, co już jest w zestawie.

Zestaw przetrwa przechodzenie po Księdze: zaznacz kilka sekcji w jednym module,
otwórz inny moduł i zaznacz kolejne. Dopóki zestaw nie jest pusty, nad
dokumentem stoją dwa przyciski:

- **Eksportuj wybrane sekcje** pobiera cały zestaw jako jeden PDF, w kolejności
  zaznaczania. Każdy rozdział zachowuje własny nagłówek, poprzedzony nazwą
  modułu, z którego pochodzi.
- **Wyczyść zestaw** opróżnia zestaw.

Zestaw jest zapamiętywany przez przeglądarkę: odśwież stronę, wróć do Księgi
jutro — nadal tam będzie, gotowy do eksportu albo do wyczyszczenia.
**Podręcznik użytkownika** i **Podręcznik administratora** mają osobne zestawy.
Nagłówki w różnych językach nazywają się inaczej, więc wybierz język przed
rozpoczęciem zbierania — sekcja zaznaczona w innym języku nie trafi do
dokumentu.

## Czytanie w innym języku

Nad tekstem, w każdej sekcji Księgi, znajdują się przyciski języków — na
przykład **EN**, **PL** i **RU**. Oferują wyłącznie języki, w których
dokumentacja rzeczywiście jest napisana, więc przycisk nigdy nie otworzy pustej
strony. Przycisk czytanego języka jest wyróżniony; kliknij inny, a ta sama
sekcja pojawi się w tym języku.

Wybór dotyczy tylko tego, co czytasz, i niczego więcej: twój profil Odoo, menu
oraz pozostałe okna zostają w twoim języku. Nie jest też zapamiętywany — otwórz
Księgę ponownie, a wróci do twojego języka. Korzystaj z niego, aby sprawdzić
sformułowanie kolegi albo przeczytać angielski oryginał, gdy tłumaczenie wydaje
się niejasne.

Aby zmienić język nie tylko czytanej strony, ale i całej reszty, zajrzyj do
następnej sekcji.

## Zmiana języka Odoo

Kliknij swoje imię w prawym górnym rogu i wybierz **Język**. Małe okno wymienia
języki zainstalowane w twojej bazie i zaznacza ten, w którym pracujesz. Wskaż
inny, a strona przeładuje się przetłumaczona: menu, przyciski, nazwy pól,
komunikaty, raporty i Księga razem z nimi.

To twoje własne ustawienie i niczyje więcej — koledzy zachowują swoje języki, a
tworzone dokumenty zachowują język osoby, do której są adresowane. To ta sama
opcja co **Język** w **Preferencjach** pod tym samym menu; wpis w menu oszczędza
tylko wyprawę do formularza preferencji.

Dwie rzeczy warto wiedzieć przed przełączeniem:

- Strona się przeładowuje, więc najpierw zakończ lub zapisz to, co edytujesz.
- Lista zawiera języki zainstalowane przez administratora. Jeśli brakuje tego,
  którego potrzebujesz, poproś administratora o dodanie; przyciski języków
  wewnątrz Księgi działają niezależnie i nie wymagają zainstalowanego języka.

## Czytanie podręczników

Otwórz **Odubook → Podręczniki**. Półka zawiera dokumenty wgrane przez administratora wraz z formatami plików. Wyszukaj dokument po tytule lub nazwie pliku i wybierz go do czytania. Po włączeniu danych demonstracyjnych dostępny jest również wielojęzyczny przykład **Sales Cube — sales management model**:

- dokumenty Markdown i zwykłego tekstu są sformatowane i pokazywane jak
  podręcznik;
- dokumenty HTML — na przykład interaktywny artefakt — działają wewnątrz strony;
- pliki PDF i obrazy są wyświetlane takimi, jakie są;
- każdy inny format (arkusz, archiwum) jest oferowany do pobrania.

Dokument może mieć kilka wersji językowych. Zawsze otwierasz wersję w języku
ustawionym w twoim profilu Odoo; gdy tłumaczenia brakuje, pokazywana jest wersja
angielska albo jedyna istniejąca. Przyciski języków nad dokumentem — **EN**,
**PL**, **RU** — przełączają ją ręcznie, dokładnie tak jak w podręcznikach;
tutaj wymieniają języki, w których sam dokument został dodany.

Przycisk **Pobierz** nad dokumentem zawsze zapisuje plik czytanej wersji.
Administrator widzi dodatkowo **Dodaj dokument** pod półką, **Usuń** obok
**Pobierz** oraz przerywany przycisk języka dla każdego brakującego tłumaczenia:
kliknięcie wgrywa to tłumaczenie. Zwykli użytkownicy czytają półkę, nie
zmieniając jej.

## Czytanie archiwum zmian

Otwórz **Odubook → Zmiany** — to pierwsze menu Księgi, więc otwarcie aplikacji
trafia właśnie tutaj. Jeden wpis to jeden moduł z jednej daty.
Przełącznik nad listą po lewej stronie oferuje trzy widoki:

- **Wg daty** to strumień chronologiczny. Wybierz miesiąc po lewej stronie i
  czytaj po prawej wszystkie zmiany tego miesiąca, na górze opublikowaną
  najpóźniej. Nagłówek każdego wpisu podaje moduł, którego zmiana dotyczy, oraz
  jej dzień. Przycisk **Wykres** obok **Archiwum zmian** jest wyłączony po otwarciu
  widoku; włącz go, a nad strumieniem pojawi się wykres pokazujący, jak
  pracowity był każdy miesiąc: jeden słupek na miesiąc, najstarsze po lewej,
  wysokość to liczba zmian. Nieprzeczytana część miesiąca jest rysowana u góry
  słupka mocniejszym kolorem, więc jedno spojrzenie mówi, ile się wydarzyło i
  ile wciąż na Ciebie czeka. Kliknij słupek, aby otworzyć ten miesiąc, a wskaż
  go, aby zobaczyć dokładne liczby. Wyłącz przycisk ponownie, a wykres zniknie;
  jest oferowany tylko w tym widoku.
- **Wg modułu** to lista modułów. Wybierz moduł, aby przeczytać całą jego
  historię.
- **Wg modułu i daty** to lista dni, najnowsze na górze, pogrupowana według
  miesięcy. Wybierz dzień, aby przeczytać wpisy wszystkich modułów zmienionych
  tego dnia.

Każdy wpis mówi, kiedy został opublikowany — kiedy zmiana dotarła na ten
serwer, a nie kiedy ktoś ją napisał — a archiwum jest uporządkowane według tej
chwili, najświeższe na górze. Data wpisu to dzień, w którym autor go złożył, i
może być starsza od publikacji: zmiana napisana w piątek, a opublikowana w
poniedziałek, stoi wśród poniedziałkowych nowości. Wpis napisany, ale jeszcze
nieopublikowany, mówi **Jeszcze nieopublikowane** i stoi ponad wszystkim
opublikowanym; na tym serwerze zobaczysz taki tylko wtedy, gdy zmiana jest
właśnie przygotowywana.

Tytuł wpisu mówi, co się zmieniło, a nie kiedy: dzień jest i tak pokazany obok,
więc wiodąca data znika z tytułu. Wpis, któremu autor nie nadał własnego tytułu,
jest tytułowany nazwą swojego modułu w obu widokach datowych, a w widoku **Wg
modułu** nie ma tytułu wcale — nazwa modułu stoi już nad całą grupą.

Obok każdego tytułu — własnego tytułu wpisu oraz tytułu otwartego miesiąca, dnia
lub modułu — stoją dwa przyciski, które pojawiają się po wskazaniu tytułu:

- przycisk PDF pobiera to, co stoi pod tym tytułem: pojedynczy wpis albo
  wszystkie wpisy otwartej grupy. Pobranie nie oznacza wpisu jako
  przeczytanego.
- przycisk odnośnika kopiuje odnośnik do tego tytułu do schowka. Otwarty gdzie
  indziej przywraca archiwum w tym samym widoku, na tej samej grupie, przy tym
  samym wpisie i w tym samym języku. Tam, gdzie przeglądarka odmawia dostępu do
  schowka — a przez zwykłe HTTP odmawia zawsze — odnośnik jest pokazywany, aby
  skopiować go ręcznie.

W każdym widoku dodane wiersze są oznaczone na zielono, a usunięte na czerwono.
Przyciski języków obok tytułu otwartego miesiąca, dnia lub modułu działają
dokładnie tak jak w podręcznikach, a samo archiwum — które wpisy istnieją i
które z nich przeczytałeś — nie zależy od języka, w którym je czytasz.

## Zbieranie kilku zmian w jeden PDF

Przycisk PDF przy wpisie eksportuje sam ten wpis. Gdy potrzebujesz kilku z nich
w jednym dokumencie — miesiąca jednego modułu albo wszystkiego, co zmieniło się
w modułach przed wydaniem — zaznacz pole wyboru przy nagłówku każdego wpisu,
którego chcesz.

Zestaw przetrwa poruszanie się po archiwum: zaznacz kilka wpisów w kronice,
przełącz się na **Według modułu** i zaznacz kolejne tam. Wpis jest pamiętany
przez swój moduł i swoją datę, więc zmiana widoku ani języka czytania nie
narusza zestawu. Dopóki nie jest pusty, przy tytule otwartej grupy stoją dwa
przyciski:

- **Eksportuj wybrane wpisy** pobiera cały zestaw jako jeden PDF, w kolejności
  zaznaczania.
- **Wyczyść zestaw** opróżnia zestaw.

Zestaw pamięta przeglądarka, więc odświeżenie strony już go nie opróżnia.
Zestaw archiwum i zestaw podręczników są trzymane osobno. Zaznaczenie wpisu nie
oznacza go jako przeczytanego.

## Nieprzeczytane wpisy i etykieta „Nowe”

Wpisy, których jeszcze nie przeczytałeś, są pogrubione. Przy miesiącu, dniu lub
module stoją dwa znaczniki: wypełniony po lewej liczy wpisy jeszcze nie
przeczytane i pojawia się tylko dopóki jakieś zostały, a blady po prawej liczy
wszystkie wpisy tej grupy. Wpis opublikowany w ciągu ostatnich trzech dni ma
dodatkowo zieloną etykietę **Nowe**.

Obie oznaczenia są osobiste: koledzy mają własną listę nieprzeczytanych. Wpis
liczy się jako przeczytany dopiero wtedy, gdy naprawdę go zobaczysz: dzień i
moduł są czytane w całości, a w strumieniu miesiąca oznaczane są tylko wpisy, do
których przewinąłeś. Wyróżnienie pozostaje do momentu przejścia do innego
miesiąca, dnia lub modułu, więc nie znika w trakcie czytania. Przycisk **Oznacz
wszystkie jako przeczytane** czyści wszystko naraz.

Wpisy starsze niż trzy miesiące nigdy nie są liczone jako nieprzeczytane, dzięki
czemu archiwum historyczne pozostaje czytelne zamiast zamieniać się w ścianę
pogrubionego tekstu.

Każdy wpis jest dostępny po angielsku, polsku i rosyjsku. Wpisy są wyświetlane
w języku twojego profilu Odoo, tak samo jak przewodniki, i można je przełączać
ręcznie przyciskami języków nad nimi.

Podręcznik użytkownika odpowiada na pytanie „co obowiązuje teraz”. Archiwum
zmian odpowiada na pytanie „co i kiedy się zmieniło”.
