<!-- i18n source=user_guide.md sha=8da3d3f0774c lang=pl -->
# Podręcznik użytkownika OduMCP

## Zanim zaczniesz

Administrator musi włączyć **MCP Active** i wybrać **Profile** na Twoim
użytkowniku Odoo. Wyłączony użytkownik, wyłączona flaga MCP lub nieaktywny
profil blokują wszystkie żądania MCP.

## Twoje klucze API MCP

OduPilot używa podpisanego tokenu każdej rozmowy zamiast osobistego klucza API. Zamknięcie lub usunięcie rozmowy odwołuje jej dostęp.

Aby podłączyć osobnego zewnętrznego klienta MCP, utwórz własny klucz API:

1. Otwórz swój profil Odoo i przejdź do **Account Security**.
2. Utwórz nowy klucz API.
3. Wpisz rozpoznawalny opis.
4. Pozostaw **Access** na wartości **MCP only**.
5. Skopiuj klucz od razu i zapisz go w menedżerze haseł.

Taki klucz jest pokazywany tylko raz. Jego unieważnienie natychmiast odłącza
korzystających z niego klientów. Klucz MCP-only nie uwierzytelnia zwykłych
wywołań RPC Odoo, a zwykły klucz **All APIs** nie uwierzytelnia API MCP.
Utworzenie, zastąpienie lub unieważnienie osobistego klucza nie wpływa na sesje
OduPilot.

## Podłączenie klienta

Skonfiguruj adres URL serwera OduMCP i użyj wygenerowanego klucza jako
tokenu bearer. Klient działa jako Twój użytkownik Odoo i jest dodatkowo
ograniczony wybranym profilem MCP: dozwolonymi firmami, modelami, polami,
operacjami, limitami rekordów i limitami żądań.

## Co potrafi konektor

O tym, do czego klient ma dostęp, decyduje Twój profil. Zapytaj administratora,
które z tych możliwości są u Ciebie włączone.

- **Poznawanie** podłączonej bazy, dostępnych modeli i ich pól.
- **Odczyt** rekordów: wyszukiwanie domeną, odczyt po id, zliczanie i
  agregacja z grupowaniem.
- **Pobranie** załącznika rekordu lub wygenerowanie raportu PDF.
- **Proponowanie zmian**: tworzenie, aktualizacja lub usuwanie rekordów;
  wiadomość w chatterze; przesłanie załącznika; wywołanie metody wyraźnie
  dopuszczonej przez administratora.
- **Zarządzanie swoimi działaniami**: zaplanowanie działania na rekordzie,
  przypisanie go komu innemu, przesunięcie terminu, przeredagowanie i zamknięcie
  z notatką podsumowującą.

## Twoje działania

Gdy profil dopuszcza działania, klient pracuje na działaniach, które należą do
Ciebie — tych utworzonych przez Ciebie i tych przypisanych Tobie. Działanie
kolegi na tym samym rekordzie pozostaje niewidoczne i nietykalne, dokładnie tak,
jak własność definiują reguły samego Odoo.

W tym zakresie klient może je czytać, zmieniać osobę odpowiedzialną, termin,
typ, temat i notatkę oraz je zamykać. Zamknięcie prosi o notatkę podsumowującą,
która zostaje jako wiadomość w chatterze rekordu, więc zakończone działanie
zostawia ślad.

Działania nigdy nie są usuwane. Nie ma odrzucania — działanie, które przestało
być potrzebne, zamyka się notatką mówiącą właśnie to. Klient nie może też
utworzyć działania jako samodzielnego rekordu: planuje je na rekordzie, a to
możliwe jest tylko tam, gdzie profil już pozwala ten rekord zmieniać.

Żądanie niedozwolone przez profil kończy się błędem `policy_denied`, a nie
cichym zwróceniem mniejszej ilości danych.

## Zmiany i zatwierdzenia

Operacje odczytu wykonują się od razu, jeśli są dozwolone. Żadna zmiana nie
trafia do Odoo w jednym kroku: najpierw podgląd, potem wykonanie.

1. Klient wysyła **podgląd** wraz z kluczem idempotencji. Odoo sprawdza plan
   względem profilu, wyznacza objęte rekordy i zapisuje zanonimizowaną różnicę.
2. Menedżer MCP ogląda dokładny plan w **OduMCP > Approval Inbox** i
   zatwierdza go albo odrzuca.
3. Klient wykonuje zatwierdzony plan. Wykonać można tylko plan zatwierdzony i
   nieprzeterminowany, i tylko raz.

Plany są grupowane według żądania, z którego przyszły. Klient zmieniający sto
rekordów wysyła ten sam **klucz partii** z każdym podglądem, a Odoo umieszcza je
wszystkie pod jednym oznaczeniem żądania, na przykład `MCP/2026/00042`. Bez
klucza partii Odoo grupuje plany jednego użytkownika i profilu, które przychodzą
blisko siebie w czasie, więc pojedyncze zadanie nadal trafia do jednego żądania.

**OduMCP > Approval Inbox** jest domyślnie pogrupowany według żądania.
Otwórz żądanie, zaznacz interesujące Cię rekordy — albo pole wyboru w nagłówku,
żeby wziąć całą grupę — i użyj **Approve Selected**. **Reject Selected** oraz
**Delete Selected Expired** działają tak samo. Sto planów jednego zadania
rozstrzygasz więc w jednym kroku zamiast stu kliknięć, a zatwierdzenie tylko
części żądania pozostaje możliwe.

Powtórzenie podglądu z tym samym kluczem idempotencji zwraca istniejący plan,
zamiast tworzyć drugi. Użycie tego klucza do innego planu jest odrzucane z
`idempotency_conflict`.

Plan wygasa po czasie approval TTL z profilu. Planu wygasłego lub odrzuconego
nie da się wskrzesić — klient musi utworzyć nowy z nowym kluczem idempotencji.

Jeśli Twój profil ma włączone **Auto Approve Low Risk**, dwie akcje pomijają
krok ręcznego zatwierdzenia i powstają już zatwierdzone: wiadomość w chatterze i
zaplanowanie działania. Klient nadal musi je jawnie wykonać, a trafiają do
audytu tak samo jak każda inna zmiana.

Zakładki **Redacted Diff** i **Result** pokazują plan jako podświetlony YAML:
jedna linia na klucz, rekordy rozdzielone myślnikiem, wartości zanonimizowane na
czerwono. Surowy JSON pozostaje dostępny w trybie dewelopera.

## Aktualizacje na żywo

Klient może subskrybować aktualizacje zasobów Twojego użytkownika. Pobiera
krótkotrwały bilet zdarzeń, a następnie odpytuje strumień zdarzeń. Odoo
powiadamia go, gdy zatwierdzenie zmienia stan albo gdy wykonana zmiana dotknęła
rekordu, dzięki czemu klient nie musi czytać wszystkiego od nowa.

## Rozwiązywanie problemów

- `mcp_access_not_configured`: poproś administratora o wybranie profilu i
  włączenie MCP na zakładce **Account Security** Twojego użytkownika.
- `inactive_mcp_access`: sprawdź, czy użytkownik, flaga MCP i profil są aktywne.
- `service_disabled`: administrator wyłączył API konektora w
  **Settings > OduMCP**.
- `policy_denied`: wybrany profil nie zezwala na żądany model, pole, operację,
  metodę lub możliwość.
- `access_denied`: prawa dostępu Odoo albo reguły rekordów odmawiają, lub
  istniejący rekord jest poza zakresem wymuszonym przez profil. Błąd wymienia
  odrzucone identyfikatory rekordów, więc wywołanie można powtórzyć bez nich.
- `field_denied`: domena wyszukiwania albo lista pól używa pola, którego profil
  nie udostępnia. Błąd nazywa te pola. Na profilu z **Partial Field Reads**
  zwykła lista pól zostaje jednak wykonana, a odpowiedź niesie blok
  `omitted_fields`: te pola są nieudostępnione, a nie puste.
- `unknown_field`: żądane pole w ogóle nie istnieje w modelu — zwykle to literówka
  albo pole z innej wersji Odoo. To nie jest problem uprawnień: dostępne nazwy
  wymienia opis modelu.
- `record_not_found`: co najmniej jeden żądany identyfikator rekordu nie
  istnieje. Błąd wymienia brakujące identyfikatory, a przy żądaniu mieszanym
  także identyfikatory rekordów istniejących, lecz niedostępnych, dzięki czemu
  wszystkie nieużyteczne identyfikatory można usunąć przed jednym ponowieniem.
- `rate_limit_exceeded` / `daily_quota_exceeded`: odczekaj przed ponowieniem lub
  poproś o większy limit.
- `payload_too_large` / `response_too_large`: żądanie albo jego wynik przekracza
  skonfigurowany limit rozmiaru; zawęź listę pól albo liczbę rekordów.
- `idempotency_conflict`: klucz idempotencji należy już do innego planu.


Tworząc klucz, wybierz termin ważności dozwolony przez Twoje grupy Odoo. Wygasłe klucze są odrzucane także przy włączonym dostępie MCP.

## Zgodność z Odoo 17

Do nowej instalacji na Odoo 17 użyj gałęzi `17.0`. Zainstaluj moduł z `addons` wraz z zadeklarowanymi zależnościami. Ta gałąź nie służy do obniżania wersji istniejącej bazy Odoo.

## Żądania przez Oduflow

Administratorzy mogą łączyć się przez Oduflow bez osobnego serwera MCP.
Przeglądaj te same plany zatwierdzania w Odoo; istniejące polityki modeli i
wymagania zatwierdzenia nadal obowiązują. Wpisy audytu korzystające z zarządzanego
klucza integracji mają `source = oduflow` oraz administratora jako użytkownika
Odoo. Wspólny klucz nie identyfikuje konkretnej osoby inicjującej żądanie.
