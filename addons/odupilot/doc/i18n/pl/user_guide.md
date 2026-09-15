<!-- i18n source=user_guide.md sha=12bbea76108b lang=pl -->
# Podręcznik użytkownika OduPilot

## Rozpoczęcie rozmowy

Otwórz Discuss → **AI Agent Chat**, wybierz dostępnego agenta i kliknij **Start Chat**. Administrator musi wcześniej przypisać profil OduPilot z modelem i danymi uwierzytelniającymi. Każda rozmowa ma własną historię i katalog roboczy. Status nad wiadomościami pokazuje inicjalizację, gotowość, pracę, oczekiwanie na zgodę, błąd lub zamknięcie.

Rozmowy znajdują się w sekcji **OduPilot** panelu bocznego Discuss. Sekcja zapamiętuje, czy jest rozwinięta. Nowy tytuł zawiera nazwę agenta i Twoje inicjały. Pierwsza odpowiedź może zastąpić nazwę agenta krótkim tematem; nazwa nadana ręcznie ma pierwszeństwo. Edytuj ją w nagłówku rozmowy.

## Pytanie o rekord

Kliknij **Ask AI** w czacie zapisanego rekordu, wpisz pytanie i potwierdź. Pytanie natychmiast pojawi się jako notatka wewnętrzna. Odpowiedź i status aktualizują tę samą notatkę. Jeśli ją usunięto, odpowiedź pojawi się w nowej notatce. Formularz zachowuje niezapisane zmiany.

Pytania korzystają z ukrytej rozmowy technicznej i nowego kontekstu AI dla każdego pytania. Nie zużywają limitu zwykłych rozmów. Rozmowa techniczna nie prosi o interaktywne zgody na narzędzia. Wymagane są zwykłe prawa dostępu do rekordu; dostęp do AI nie nadaje dodatkowych uprawnień Odoo.

## Wiadomości i pliki

Wpisz i wyślij wiadomość. Gdy w rozmowie jesteście tylko Ty i bot, wiadomości automatycznie trafiają do AI. Przy kilku użytkownikach wewnętrznych skieruj wiadomość do AI przez wzmiankę o bocie. Wyślij `/abort` zgodnie z tymi samymi zasadami, aby zatrzymać żądanie.

Dołączaj pliki zwykłym edytorem Discuss. Most kopiuje dozwolone załączniki do katalogu sesji i lokalnie konwertuje obsługiwane dokumenty. Nieobsługiwane formaty podlegają skonfigurowanym ograniczeniom. Strumień odpowiedzi pokazuje tekst i zwijane kroki narzędzi lub rozumowania; zapisana odpowiedź obsługuje Markdown, tabele i linki. Wygenerowany HTML jest oczyszczany.

## Decyzje i odzyskiwanie

Karta zgody opisuje operację i żądany dostęp. **Allow once**, **Always** lub **Reject** wysyła decyzję do mostu. Karta pokazuje autora decyzji i status dostarczenia. Decyzje są zapisywane w dzienniku audytu.

Po przerwaniu żądania karta odzyskiwania może zaoferować **Retry** lub **Dismiss**. Przed ponowieniem przeczytaj informację o narzędziach: operacja zewnętrzna mogła już zostać wykonana. Żądanie przerwane przed użyciem narzędzi może zostać automatycznie ponowione jeden raz.

## Inni uczestnicy i powiadomienia

Właściciel lub administrator może zapraszać aktywnych użytkowników wewnętrznych. Goście nie mogą dołączać. Do rozmów z drzewami roboczymi programisty mogą dołączać tylko administratorzy. W aktywnej rozmowie właściciel i bot AI są chronieni przed usunięciem. Opuszczenie własnej rozmowy zamyka jej sesję AI; inny uczestnik może wyjść bez zamykania sesji.

Odpowiedź lub prośba o decyzję może wyświetlić trwałe powiadomienie, gdy rozmowa nie jest widoczna. **Open conversation** otwiera właściwą rozmowę. Kroki techniczne nie wywołują tych powiadomień. Rozmowy programistyczne otwierają się w Discuss.

## AI Developer

Administratorzy mogą otworzyć **AI Developer** z menu narzędzi programisty. Wpisz żądanie; **Dictate** jest dostępne, gdy przeglądarka pozwala nagrywać mikrofon w bezpiecznym kontekście. Zatrzymaj nagrywanie, aby otrzymać edytowalną transkrypcję. Limit nagrania wynosi pięć minut. Dźwięk jest wysyłany do transkrypcji bez zapisywania jako załącznik Odoo.

Żądanie zawiera kontekst bieżącego ekranu. Skonfigurowany profil programisty tworzy izolowane drzewo robocze Git. AI może najpierw sklasyfikować problem jako pytanie o ustawienia lub zmianę kodu; zmianę kodu można przypisać odpowiedzialnemu programiście. Linki do środowiska i publikacji pojawiają się, gdy dostarczą je podłączone usługi. Operacje te wymagają odpowiedniego profilu i infrastruktury zewnętrznej.

## Dostęp i rozwiązywanie problemów

Aby udostępnić narzędzia Odoo, administrator włącza **MCP Active** i wybiera profil MCP. OduPilot tworzy podpisany token każdej sesji; nie wymaga stałego osobistego klucza API. Wywołania narzędzi podlegają Twoim uprawnieniom Odoo i politykom MCP.

Jeśli sesja pozostaje w inicjalizacji, poproś administratora o sprawdzenie mostu. Przy błędzie sprawdź status i kartę odzyskiwania. Zamknięcie sesji odwołuje jej dostęp AI i kolejkuje usunięcie katalogu roboczego, zachowując historię Discuss. Opcjonalni agenci, na przykład uzgadnianie płatności, wymagają odpowiednich modułów biznesowych i skonfigurowanych polityk.
