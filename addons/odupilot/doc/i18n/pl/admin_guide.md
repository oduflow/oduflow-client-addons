<!-- i18n source=admin_guide.md sha=7fa4e8a08dd8 lang=pl -->
# Podręcznik administratora OduPilot

## Instalacja na Odoo 17

Zainstaluj `odupilot` z katalogu `addons` tego repozytorium. Zależności obejmują `mail`, `auth_totp` i `odumcp`. Przed załadowaniem modułu zainstaluj pakiety Python z `.oduflow/requirements.txt`. Moduły Odoo 15 `ai_chat`, `streams` i `bus_actions` nie są wymagane.

Jest to port do instalacji na Odoo 17. Nie przenosi istniejącej bazy Odoo 15 ani nie zmienia nazw zainstalowanych rekordów bazy. Importowane wpisy zmian opisują historię modułu źródłowego.

## Infrastruktura

Zbuduj i wdroż `addons/odupilot/deploy/docker-compose.yml`. Skopiuj jego `.env.example` do magazynu sekretów i ustaw dane Odoo, OpenCode Basic Auth, nazwy wolumenów i liczbowe UID/GID. OpenCode i most współdzielą prywatną sieć i trwały wolumen `/workspace`. Odoo przechowuje ścieżki i konfigurację; nie musi montować tego wolumenu. Port OpenCode `4096` powinien pozostać prywatny.

Plik compose buduje lokalny most i przypięty obraz OpenCode. Zawiera lokalną konwersję dokumentów przez AnyDoc. Obraz pod zmienioną nazwą nie musi istnieć w rejestrze. Budowę obrazów, przygotowanie katalogów i kontrole uruchomienia opisuje README wdrożenia. Profile programistyczne wymagają dodatkowo danych Git i skonfigurowanych narzędzi środowiska Oduflow.

Most loguje się do Odoo przez osobnego użytkownika wewnętrznego z grupą **OduPilot Bridge Service**. Nadaj ją w technicznych ustawieniach użytkowników i grup. Otwiera ona metody RPC zwracające dane uwierzytelniające wdrożenia, więc przypisuj ją wyłącznie kontu mostu. Same uprawnienia administratora nie spełniają tej kontroli. Instalacja nie zmienia grup istniejących użytkowników.

## Profile i agenci

W Settings → **OduPilot** skonfiguruj profile, agentów i serwery MCP. Profil wybiera model, klucz LiteLLM, typ katalogu roboczego, limit sesji, dostępność agentów i ustawienia programisty. Wspólny bazowy URL AI ustaw w konfiguracji OduPilot. Przypisz profil na stronie bezpieczeństwa użytkownika.

Agent określa instrukcje, reguły narzędzi i serwery MCP. Zwykłe rozmowy mogą uruchamiać tylko agenci dostępni dla profilu użytkownika. Agenci przeznaczeni wyłącznie dla MCP są udostępniani przez MCP zamiast wyboru czatu. Opcjonalne uzgadnianie płatności wymaga odpowiednich modułów księgowych i płatniczych.

Dla narzędzi Odoo włącz **MCP Active** i przypisz użytkownikowi profil MCP. Skonfiguruj serwer MCP z podstawieniem tokenu sesji w nagłówkach. Każda sesja otrzymuje podpisany token związany z właścicielem i profilem. Odwołanie dostępu i zmiany polityk są sprawdzane przy kolejnych wywołaniach. Osobiste klucze API MCP są niezależne i muszą uwzględniać terminy ważności Odoo 17.

Profile programistyczne z drzewami roboczymi potrzebują URL repozytorium, gałęzi bazowej, tokenu GitHub i konfiguracji środowiska. Ustaw **Developers Profile** dla menu programisty oraz opcjonalnie **Responsible Developer**. Żądanie sklasyfikowane jako praca programistyczna dodaje tego administratora do rozmowy i wysyła trwałe powiadomienie OduPilot.

## Dyktowanie

Dyktowanie korzysta z danych LiteLLM profilu i wspólnego bazowego URL AI. Model transkrypcji ustaw parametrem systemowym `odupilot.transcription_model`; domyślna wartość to `whisper-1`. Przeglądarka wymaga bezpiecznego kontekstu i zgody na mikrofon. Limity wynoszą pięć minut i 25 MiB na nagranie. Dźwięk nie jest zapisywany jako załącznik. Transkrypcja zwraca tekst do edycji przed wysłaniem żądania.

## Połączenie i monitoring

Most odpytuje `/odupilot/bridge/poll` przez zwykły adres HTTP Odoo. Metoda jest dostępna tylko dla konta technicznego; nie można wybierać dowolnych kanałów magistrali. Po pustej odpowiedzi most czeka sekundę. Trwała kolejka poleceń XML-RPC pozostaje źródłem prawdy. Trasa długiego odpytywania Odoo 15 nie jest używana. Dla zdarzeń Discuss w przeglądarce skonfiguruj standardowy WebSocket Odoo 17.

Serwer OduMCP odpytuje `/odumcp/v1/events` z krótkotrwałym biletem zdarzeń i czeka sekundę po pustej odpowiedzi. Żądania widzą wyłącznie prywatny kanał właściciela biletu. Wdrażaj dołączoną wersję serwera MCP razem z tym modułem.

W **Monitoring** sprawdzaj stan mostu/OpenCode i ostatnie błędy; do analizy pracy używaj **Sessions**, **Commands** i dziennika działań agentów. Most ponownie łączy się ze strumieniem OpenCode i pobiera zakończone wiadomości z usuwaniem duplikatów. Po ponownym połączeniu uzgadnia też sesje. Polecenia są dostarczane kolejno i mają identyfikatory idempotencji.

## Odzyskiwanie i przechowywanie

Ustaw limit czasu zajętej sesji oraz okresy przechowywania zdarzeń i zamkniętych sesji w ustawieniach OduPilot. Zadanie uruchamiane co pięć minut sprawdza przeterminowane żądania. Kolejkuje przerwanie i może automatycznie ponowić żądanie raz, jeśli nie użyto narzędzi. W przeciwnym razie uczestnik wybiera **Retry** lub **Dismiss**. Spóźniona odpowiedź zamyka otwarte rekordy odzyskiwania i anuluje niepotrzebne ponowienia.

Zamknięcie sesji odwołuje jej token i kolejkuje usunięcie katalogu roboczego. Polityka przechowywania usuwa rekordy techniczne, zachowując kanały i wiadomości Discuss. Okres równy zero oznacza przechowywanie bezterminowe. Most musi pozostać dostępny do obsługi poleceń czyszczenia.

## Weryfikacja

Uruchom testy Odoo dla `/odupilot,/odumcp`, testy mostu w `addons/odupilot/deploy` i testy serwera MCP w `addons/odumcp/deploy/odumcp_server`. Testy przeglądarkowe używają izolowanej bazy Odoo. Rzeczywisty dostawca, zewnętrzne repozytorium Git i środowisko programisty wymagają osobno skonfigurowanych usług; lokalne atrapy nie weryfikują ich danych uwierzytelniających.

## Zgodność z Odoo 17

Do nowej instalacji na Odoo 17 użyj gałęzi `17.0`. Zainstaluj moduł z `addons` wraz z zadeklarowanymi zależnościami. Ta gałąź nie służy do obniżania wersji istniejącej bazy Odoo.
