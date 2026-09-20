<!-- i18n source=admin_guide.md sha=23bf6030f2ed lang=pl -->
# Podręcznik administratora OduMCP

## Role bezpieczeństwa

- **MCP Auditor** może przeglądać profile, zatwierdzenia i wpisy audytu.
- **MCP Manager** może konfigurować profile, włączać użytkowników i decydować o
  zatwierdzeniach.

Nie używaj konta administratora jako użytkownika MCP. Prawa dostępu Odoo, reguły
rekordów, dozwolone firmy i profil MCP działają łącznie: profil może wyłącznie
zawęzić to, na co przypisany użytkownik Odoo i tak ma pozwolenie.

## Włączenie MCP dla użytkownika

1. Otwórz **Settings > Users & Companies > Users** i wybierz użytkownika.
2. Przejdź na istniejącą zakładkę **Account Security**.
3. Włącz **MCP Active**.
4. Wybierz **Profile**.
5. Zapisz użytkownika.

Zapisanie tych pól nie tworzy stałego klucza API. Przy uruchamianiu każdej
rozmowy OduPilot sprawdza użytkownika, flagę i profil oraz wydaje własny podpisany token
sesji, który jest unieważniany po zamknięciu rozmowy. Osoba podłączająca
zewnętrznego klienta MCP tworzy osobisty klucz w sekcji **Preferencje >
Zabezpieczenia konta**, gdzie sekret jest wyświetlany jeden raz. Taki klucz
działa na punktach końcowych MCP i nigdzie indziej, a zwykły klucz **All APIs**
jest przez nie odrzucany.

Nie ma osobnego rekordu User Access ani osobnego menu. Każdy użytkownik
przechowuje dokładnie jedną flagę MCP i jeden profil bezpośrednio. Liczniki
użycia nie są zapisywane na użytkowniku; limity minutowy i dzienny wyliczane są z
niezmiennych wpisów audytu.

**MCP Active** i **Profile** to celowo dwa pola. Profil mówi, co użytkownik może
robić; flaga mówi, czy w ogóle może cokolwiek. Flaga jest domyślnie wyłączona,
więc sam profil niczego nie otwiera — profil pochodzący z szablonu użytkownika
lub z kopii nie nadaje dostępu samodzielnie. Odwrotna kombinacja jest odrzucana:
włączenie flagi bez profilu zgłasza błąd **Select an MCP profile before enabling
MCP access**.

## Konfiguracja profilu bezpieczeństwa

Otwórz **OduMCP > Security Profiles**. Profil działa w trybie default-deny:
bez jawnej Model Policy i bez szerszego dostępu domyślnego nie jest udostępnione
nic.

### Profil i limity

- **Allowed Companies** przecina się z firmami użytkownika konektora. Pusta
  lista oznacza wszystkie firmy, które użytkownik już ma. Brak części wspólnej
  to błąd, a nie ciche pełne uprawnienia.
- **Max Records Per Call** ogranicza wyniki wyszukiwania, odczytu, agregacji i
  raportów.
- **Max Batch Size** ogranicza liczbę rekordów, które może objąć jeden plan
  tworzenia, aktualizacji lub usunięcia.
- **Rate Limit Per Minute** i **Daily Quota** liczone są z wierszy audytu.
  Zerowy limit dzienny wyłącza kontrolę dzienną; granica doby to UTC.
- **Approval TTL Minutes** określa, jak długo plan zmiany pozostaje wykonywalny.

### Domyślny dostęp do modeli

To tryb zapasowy stosowany wyłącznie do modeli bez jawnej Model Policy.

- **Explicit policies only** — zalecana wartość domyślna. Nic poza zakładką
  Model Policies nie jest osiągalne.
- **Read any accessible model** — odczyt oraz, przy włączonym **Aggregate**,
  agregacja każdego nietymczasowego modelu, który użytkownik Odoo może czytać.
- **Read and update any accessible model** — dodatkowo zezwala na aktualizacje.

**Create on Any Accessible Model** i **Delete from Any Accessible Model**
dokładają do tego samego trybu zapasowego dwie kolejne operacje. Wszystkie nadal
wymagają odpowiedniego prawa dostępu u użytkownika konektora, a każda zmiana
wciąż przechodzi przez zatwierdzenie.

W trybie zapasowym pola o nazwach przypominających sekrety (`password`, `pass`,
`token`, `api_key`, `secret`, `private`, `credential`, `authorization`) oraz
wszystkie pola binarne są ukryte, a zapis jest dodatkowo ograniczony do pól
niebędących tylko do odczytu i nietechnicznych.

Tryb zapasowy nigdy nie obejmuje:

- modeli tymczasowych (kreatorów);
- `ir.config_parameter`, `res.users.apikeys` oraz samych modeli OduMCP —
  tych nie da się udostępnić w ogóle, nawet jawną polityką.

Na modelach bezpieczeństwa tryb zapasowy działa wyłącznie w trybie odczytu,
niezależnie od wybranego wariantu:

- `base.automation`, `ir.actions.server`, `ir.cron`, `ir.mail_server`,
  `ir.model.access`, `ir.rule`, `ir.ui.view`, `res.groups` — odczyt jedynie
  pokazuje reguły, którym konektor i tak podlega, natomiast zapis do nich
  omijałby tę warstwę polityk; jawna Model Policy nadal może udostępnić je
  świadomie do zapisu;
- `res.users` — model jest czytelny, ale nigdy nie jest tworzony, zapisywany ani
  usuwany, bo to zmienia przynależność do grup.

Do odczytu nadal potrzebne jest odpowiednie prawo dostępu Odoo u użytkownika
konektora: `ir.model.access` i `ir.rule` są zastrzeżone dla menedżerów praw
dostępu, a `ir.ui.view`, `ir.cron`, `ir.mail_server`, `base.automation`
i `ir.actions.server` — dla użytkowników Ustawień.

### Możliwości

Każda możliwość włącza lub wyłącza jedną konkretną operację. Same z siebie nic
nie dodają — polityki modeli i pól obowiązują ponad nimi.

| Możliwość | Na co faktycznie zezwala |
| --- | --- |
| **Schema** | Opis pól modelu. Lista dozwolonych modeli jest dostępna zawsze. |
| **Aggregate** | Agregację z grupowaniem. Polityka modelu może ją wyłączyć dla jednego modelu. |
| **Reports** | Wygenerowanie raportu PDF dla maksymalnie 20 rekordów, jeśli profil może czytać model raportu. |
| **Attachments** | Pobranie załącznika czytelnego rekordu i przesłanie załącznika do rekordu dostępnego do zapisu. |
| **Chatter** | Opublikowanie wiadomości w chatterze rekordu dostępnego do zapisu, w modelu z chatterem. |
| **Activities** | Pełne zarządzanie własnymi działaniami konektora: planowanie, odczyt, aktualizację i zamykanie. Patrz niżej. |
| **Auto Approve Low Risk** | Tworzenie planów wiadomości w chatterze i zaplanowanych działań od razu jako zatwierdzonych. |
| **Partial Field Reads** | Odpowiedź na odczyt dostępnymi kolumnami zamiast odmowy, gdy lista pól wymienia także pole, którego profil nie udostępnia. |

Trzy z nich są węższe, niż sugerują nazwy:

- **Activities** jest ograniczona własnością, a nie modelem. Otwiera
  `mail.activity` tylko dla działań, które użytkownik konektora utworzył albo
  które są do niego przypisane — dokładnie tak własność definiuje rdzeniowa
  reguła `mail_activity_rule_user`. Działania współpracowników na tych samych
  rekordach pozostają niewidoczne.
- **Auto Approve Low Risk** to nie „zatwierdzaj wszystko, co wygląda
  niegroźnie”. Plan jest zatwierdzany automatycznie tylko wtedy, gdy jego
  wyliczone ryzyko jest niskie **oraz** jego akcją jest wiadomość w chatterze
  albo zaplanowane działanie. Poziomy ryzyka są zapisane w kodzie: tworzenie,
  aktualizacja i przesłanie załącznika to średnie, usunięcie to wysokie, chatter
  i działanie to niskie, a wywołanie metody przyjmuje poziom ryzyka swojej
  Method Policy. Niskiego ryzyka wywołanie metody nigdy więc nie jest
  zatwierdzane automatycznie.

- **Partial Field Reads** przycina wyłącznie zwykłą listę pól. Nieudostępnione
  pole użyte w domenie wyszukiwania albo w sortowaniu nadal kończy się odmową,
  bo jego pominięcie zwróciłoby inny zbiór rekordów, a nie te same rekordy z
  mniejszą liczbą kolumn; zapis nie jest przycinany nigdy. Odczyt, w którym
  wszystkie pola są nieudostępnione, także kończy się odmową, więc klient nigdy
  nie dostaje pustego sukcesu. Odpowiedź niesie blok `omitted_fields` z nazwami
  pominiętych pól.

  Zostaw to wyłączone dla profilu, którego allowlisty są prawdziwą kontrolą
  dostępu: klient, który dostaje dane wraz z notatką, może zgłosić
  nieudostępnione pole jako puste zamiast jako niedostępne. Włącz dla szerokiego
  profilu wewnętrznego, gdzie oszczędzone wywołanie jest warte więcej niż ścisła
  odmowa.

Automatyczne zatwierdzenie usuwa wyłącznie kliknięcie człowieka. Klient nadal
musi wykonać podgląd, a potem wykonanie, i oba kroki trafiają do audytu.

#### Co otwiera Activities

Przy włączonej możliwości — i o ile jawna Model Policy dla `mail.activity` jej
nie nadpisuje — profil daje użytkownikowi konektora:

| Operacja | Dozwolona | Jak |
| --- | --- | --- |
| Odczyt | tak | `records.search`, `records.read`, `records.count` oraz agregacja przy włączonym **Aggregate** |
| Tworzenie | przez rekord nadrzędny | `activity.schedule`, który wymaga prawa zapisu na rekordzie, do którego działanie jest dołączane |
| Aktualizacja | tak | `activity.update` na `activity_type_id`, `summary`, `note`, `date_deadline`, `user_id` |
| Zamknięcie | tak | `activity.done`, który wpisuje notatkę do chattera rekordu |
| Usunięcie | nigdy | `record.delete` na `mail.activity` jest odrzucany, nie ma też akcji anulowania |

W Odoo 19 `activity.done` używa `_action_done`, aby opublikować notatkę i zakończyć działanie. Zakończone działania mogą być archiwizowane. Bezpośrednie usuwanie przez MCP pozostaje zabronione, aby zakończenie zachowało ślad audytu.

Dwa pola celowo nie są zapisywalne: `res_model` i `res_id`. Przeniesienie
działania na inny rekord dołączyłoby je do rekordu, którego profil może nie mieć
prawa dotykać, więc zmiana celu jest odrzucana z `field_denied`.

Bezpośredni `record.create` na `mail.activity` jest odrzucany z tego samego
powodu: `activity.schedule` sprawdza prawo zapisu na modelu nadrzędnym, a gołe
utworzenie tego nie zrobi.

Jawna Model Policy dla `mail.activity` nadal nadpisuje wszystko powyższe —
użyj jej, gdy profil naprawdę potrzebuje innego zakresu, łącznie z usuwaniem.

### Polityki modeli

Zakładka **Model Policies** służy do reguł i wyjątków dla konkretnych modeli.
Dla każdego modelu można ustawić:

- dozwolone operacje: odczyt, agregację, tworzenie, zapis, usuwanie;
- listy **Readable Fields** i **Writable Fields** — wszystko, czego na nich nie
  ma, jest niewidoczne i niezapisywalne, także w domenach wyszukiwania i w
  grupowaniu; `id` i `display_name` są czytelne zawsze. Obie listy podpowiadają
  wyłącznie pola modelu polityki; aby dopuścić je wszystkie, otwórz
  **Search More...**, zaznacz pole wyboru w wierszu nagłówka i potwierdź
  **Select all N**;
- **Allow Binary Read/Write**, aby dopuścić na te listy pola binarne;
- **Forced Domain**, czyli domenę Odoo w JSON dołączaną przez AND do każdego
  wyszukiwania i sprawdzaną ponownie po zmianie, żeby zmiana nie wyprowadziła
  rekordu poza zakres;
- **Max Records**, który może wyłącznie obniżyć limit profilu.

Wrażliwe pod względem bezpieczeństwa modele OduMCP i modele poświadczeń są
tu również odrzucane.

### Dozwolone metody

Zakładka **Allowed Methods** to jedyny sposób, by pozwolić klientowi wywołać
metodę biznesową. Domyślnie nie da się wywołać niczego, a metody prywatne są
odrzucane zawsze. We wpisie definiuje się model, nazwę metody, poziom ryzyka,
ile rekordów może otrzymać, czy można ją wywołać bez identyfikatorów rekordów,
czy dozwolone są argumenty pozycyjne, dokładne nazwy dopuszczonych argumentów
nazwanych oraz maksymalny rozmiar argumentów.

### Użytkownicy

Zakładka **Users** przypisuje profil użytkownikom bezpośrednio i odzwierciedla
pole z formularza użytkownika.

## Przegląd zmian

Otwórz **OduMCP > Approval Inbox**. Lista jest pogrupowana według
**Request**: wszystkie plany, które klient utworzył dla jednego zadania, mają to
samo oznaczenie żądania, więc zadanie obejmujące sto rekordów przeglądasz i
rozstrzygasz jako jedną grupę. Zaznacz plany — albo pole wyboru w nagłówku po
otwarciu grupy — i użyj **Approve Selected**, **Reject Selected** lub **Delete
Selected Expired**. Okno potwierdzenia wypisuje, co zostanie przetworzone, i ile
zaznaczonych rekordów zostanie pominiętych, bo ich stan nie pasuje do akcji.

Przed zatwierdzeniem sprawdź
zanonimizowaną różnicę, model docelowy, ryzyko, termin wygaśnięcia, użytkownika
i profil. Wpisy zatwierdzeń są niezmienne; po odrzuceniu lub wygaśnięciu klient
musi utworzyć nowy plan. Zatwierdzony plan można wykonać tylko raz i tylko przed
wygaśnięciem.

Zakładki **Redacted Diff**, **Result** i **Integrity** prezentują zapisane
migawki jako podświetlony YAML zamiast surowego JSON-a; **Integrity** pokazuje
dodatkowo przesłany payload, a każda zanonimizowana wartość jest oznaczona na
czerwono. Włącz tryb dewelopera, aby zobaczyć obok każdego bloku źródłowy JSON,
na przykład po to, by skopiować go do zgłoszenia.

Zapisany payload jest hashowany. Jeśli w chwili wykonania nie zgadza się ze
swoim hashem, plan kończy się błędem zamiast się wykonać.

## Audyt i limity

Otwórz **OduMCP > Audit Log**, aby sprawdzić wyniki żądań. Zapisywane jest
każde żądanie — udane, odrzucone i błędne — wraz z operacją, modelem,
identyfikatorami rekordów, kodem statusu, kodem błędu, czasem trwania, adresem
zdalnym i user agentem. Samo ciało żądania nie jest przechowywane; zapisywany
jest tylko jego hash i krótkie podsumowanie. Odczyt częściowy zapisuje dodatkowo
pominięte pola, więc żądanie zaliczone jako sukces nadal pokazuje działanie
polityki. Wiersze audytu są niezmienne i
zasilają kontrole limitu minutowego i dziennego. Rekordy użytkowników nie
duplikują sum żądań, sum niepowodzeń ani czasu ostatniego użycia. **Target
Records** wypisuje objęte identyfikatory jako YAML, a surowy JSON pozostaje w
trybie dewelopera.

## Ustawienia globalne

W **Settings > OduMCP** włącza się lub wyłącza control API oraz ustawia
limity payloadu, danych binarnych, retencji, grupowania żądań i biletów zdarzeń. Wyłączenie API
pozostawia wszystkie ustawienia MCP użytkowników bez zmian i sprawia, że każda
uwierzytelniona operacja zwraca `service_disabled`.

**Request Grouping Window (minutes)** decyduje, jak grupowane są plany bez
jawnego klucza partii. Plany tego samego użytkownika konektora i profilu
dołączają do ostatniego żądania, dopóki między nimi mija mniej niż tyle minut;
domyślnie jest to 10. Zero umieszcza każdy plan w osobnym żądaniu. Klienta,
który wysyła klucz partii, to ustawienie nie dotyczy.

Retencję realizuje autovacuum Odoo: wiersze audytu starsze niż okno retencji
audytu oraz zakończone zatwierdzenia starsze niż okno retencji zatwierdzeń są
usuwane, a przeterminowane plany oznaczane jako wygasłe. Nic innego nie może
tych wierszy usunąć.

## Wyłączanie dostępu

Wyłącz **MCP Active**, aby zatrzymać dostęp bez usuwania profilu. Użytkownik z
zachowanym profilem i wyłączoną flagą to wspierany stan zawieszenia, a
przywrócenie dostępu to jedno pole wyboru. Jest to lepsze od pozostałych opcji:
wyczyszczenie profilu gubi informację o tym, który profil nadano, archiwizacja
profilu zatrzymuje wszystkich, którzy go używają, a archiwizacja użytkownika
zamyka mu całe Odoo. Klucze osobiste pozostają nietknięte: to własne
poświadczenia użytkownika, a wyłączona flaga i tak je odrzuca. W razie
ujawnienia danych usuń takie klucze na karcie **Account Security** użytkownika.
Istniejące tokeny sesji OduPilot są odrzucane natychmiast. Każde z tych działań unieważnia także wydane bilety zdarzeń.

Usunięcie użytkownika z karty **Users** profilu to ten sam odbiór dostępu
widziany z drugiej strony: profil i flaga znikają razem.

## Gdy klient zgłasza brak dostępu

Wywołujący bez dostępu MCP otrzymuje `403` z `/odumcp/v1/*` z jednym z
dwóch kodów: `mcp_access_not_configured`, gdy profil nie jest wybrany,
oraz `inactive_mcp_access`, gdy nieaktywny jest użytkownik Odoo, flaga lub
profil. Serwer MCP zgłasza oba przypadki swojemu klientowi jako `401`, więc
klient taki jak OpenCode w ogóle nie udostępnia narzędzia Odoo. W czacie wygląda
to na brakujący serwer MCP, choć serwer odmawia jednemu użytkownikowi — dlatego
najpierw sprawdź oba pola użytkownika, a dopiero potem serwer i klucz API sesji.
OduPilot nie wymaga stałego klucza w **Account Security**: dla każdej rozmowy
tworzy i unieważnia osobny klucz.


## Wdrożenie na Odoo 19

Zainstaluj `odumcp` z `addons`; użyj Oduflow lub dołączonego serwera MCP. Adres zdarzeń `/odumcp/v1/events` używa uwierzytelnionego krótkiego odpytywania; serwer czeka sekundę po pustej odpowiedzi. Osobiste klucze API wymagają prawidłowych terminów ważności Odoo 19. Ten port nie przenosi bazy Odoo 15.

## Identyfikator instalacji

Zainstaluj `odumcp` jako nowy moduł. Używa on modeli i ustawień `odumcp.*`, tras API `/odumcp/v1/`, pakietu Python `odumcp_server` oraz zmiennych serwera `ODUMCP_*`. Migracja wcześniejszej instalacji nie jest obsługiwana. Odinstaluj wcześniejszy moduł przed wdrożeniem tego kodu; odinstalowanie usuwa również moduły zależne i ich dane. Następnie zainstaluj ponownie potrzebne moduły zależne. Przed użyciem przykładu Compose zbuduj lokalnie obraz serwera o nowej nazwie (`docker compose -f docker-compose.example.yml up --build -d`); publikacja obrazu jest osobną operacją.

## Integracja produkcyjna z Oduflow

Oduflow może wywoływać moduł bezpośrednio; osobny serwer MCP jest opcjonalny.
Przy tworzeniu środowiska produkcyjnego Odoo 19 Oduflow instaluje moduł i
rejestruje poświadczenie z konfiguracji jako klucz API administratora tylko do MCP.
Zarządzany klucz ma nazwę **Oduflow production (managed)**. Odoo przechowuje tylko
skrót hasła klucza; jawna wartość pozostaje w konfiguracji Oduflow.

Lokalna operacja konfiguracji zastępuje wyłącznie zarządzany klucz. Osobiste klucze
API pozostają ważne. Istniejące profile MCP, polityki i zawieszony dostęp nie są
zmieniane. Administrator bez profilu otrzymuje profil tylko do odczytu; przed
użyciem planów zmian biznesowych jawnie skonfiguruj uprawnienia zapisu.

Po zmianie poświadczenia produkcyjnego i ponownym uruchomieniu Oduflow użyj
`sync_production_mcp`, aby zsynchronizować jedno lub wszystkie środowiska
produkcyjne zespołu. Sprawdź każdy wynik i ponów nieudane operacje po naprawie
lub uruchomieniu środowisk. Każda baza rotuje klucz osobno; stary klucz pozostaje
ważny do pomyślnej synchronizacji. Przywrócenie kopii bazy może przywrócić stary
klucz, więc po nim również wykonaj synchronizację. Usunięcie poświadczenia tylko
z Oduflow nie unieważnia go w Odoo; usuń zarządzany klucz API, wycofując integrację.

Żądania uwierzytelnione zarządzanym kluczem zapisują `source = oduflow` w dzienniku
audytu. Oznacza to poświadczenie, a nie konkretną osobę ani zweryfikowane źródło
sieciowe, i nie pozwala omijać polityk. Zatwierdzanie zmian biznesowych pozostaje
w Odoo; operacje infrastruktury produkcyjnej autoryzuje osobno Oduflow.
