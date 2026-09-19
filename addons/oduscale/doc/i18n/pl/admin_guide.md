<!-- i18n source=admin_guide.md sha=3b2463565c49 lang=pl -->
# Podręcznik administratora Oduscale

Oduscale zarządza dostępem na istniejącym serwerze Headscale. Przed rejestracją
pracowników wdroż osobno serwer sterowania, politykę VPN i bramę Odoo.

## Instalacja i przydzielanie uprawnień

Dodaj katalog `addons/` repozytorium do `addons_path` i zainstaluj `oduscale`.
Zależności to `hr`, `mail` i pakiet Python `requests`. Zainstaluj `odubook`, aby
wyświetlać tę dokumentację w Odoo; nie jest wymagany do zarządzania VPN.

Przyznaj odpowiedzialnym użytkownikom **Oduscale / Manage employee VPN access**.
Ta rola obejmuje również uprawnienia pracownika działu kadr. Administratorzy ustawień
dziedziczą rolę Oduscale. Osoby zarządzające dostępem mogą obsługiwać dostęp pracowników
i czytać konfigurację serwerów; tylko administratorzy ustawień mogą tworzyć i edytować
serwery oraz widzieć nazwę zmiennej klucza API. Reguły firm ograniczają serwery,
połączenia, urządzenia i historię kluczy do firm dozwolonych użytkownikowi. Pracownik
i serwer w połączeniu muszą należeć do zgodnych firm.

## Konfiguracja serwera Headscale

Otwórz **Oduscale → Headscale Servers**, utwórz serwer i skonfiguruj pola:

| Pole | Przeznaczenie |
| --- | --- |
| Name / Company | Nazwa serwera i firma będąca jego właścicielem. |
| API URL | Adres Headscale osiągalny z Odoo, bez `/api/v1`. |
| API Key Env | Zmienna środowiskowa z tokenem API; domyślnie `ODUSCALE_API_KEY`. |
| Login URL | Publiczny adres HTTPS serwera sterowania dostępny dla klientów Tailscale. |
| Odoo URL | Opcjonalny adres Odoo dostępny przez bramę VPN. |
| Key Lifetime Minutes | Ważność jednorazowego klucza: 5–1440 minut; domyślnie 60. |

Adresy muszą używać HTTP(S) i nie mogą zawierać danych uwierzytelniających, parametrów
zapytania ani fragmentu. Adres logowania wymaga HTTPS. Umieść token API w środowisku
procesu Odoo, a nie w rekordzie serwera; używaj osobnych nazw zmiennych dla różnych
serwerów. Kliknij **Test connection**, aby sprawdzić dostęp do API użytkowników
Headscale. Nie testuje to trasy VPN klienta ani bramy Odoo.

## Obsługa i przywracanie działania

- Zaplanowane działanie **Oduscale: synchronize employee devices** uruchamia się
  co 5 minut jako użytkownik systemowy. Upewnij się, że obsługa cron Odoo jest włączona.
- Sprawdzaj **Last Sync** i **Last Error** na serwerze. Obsłużony błąd synchronizacji
  jest zapisywany; udana synchronizacja serwera go usuwa.
- Użyj **Synchronize** na serwerze dla wszystkich jego połączeń. Zaplanowane działanie
  cofa również aktywny dostęp zarchiwizowanych pracowników lub powiązanych użytkowników.
- Żądania Headscale są poza transakcją bazy Odoo. Nieudana operacja mogła częściowo
  zmienić stan zdalny. Przywróć usługę i ponów operację; pełne cofnięcie ponownie odczytuje
  zdalne klucze i urządzenia, także zasoby nieobecne w lokalnej pamięci podręcznej.
- Archiwizacja pracownika lub powiązanego użytkownika kończy się błędem, jeśli cofnięcie
  dostępu się nie powiedzie. Usuń błąd Headscale i powtórz archiwizację.
- Wymień token API w środowisku Odoo przed wygaśnięciem i sprawdź go przez
  **Test connection**. Nie umieszczaj tokenów API i poleceń połączenia w Git ani raportach.

## Sekrety i granice dostępu

Klucze rejestracji są jednorazowe i tworzą trwałe urządzenia. Ich wygaśnięcie jest
terminem rejestracji, a nie limitem czasu sesji. Unieważnij klucz, aby zatrzymać
rejestrację; cofnij dostęp urządzenia lub cały dostęp, aby usunąć istniejące połączenia VPN.

Okno rejestracji przechowuje polecenie z sekretem w rekordzie tymczasowym z czasem
życia jednej godziny, usuwanym przez mechanizm czyszczenia rekordów tymczasowych Odoo.
Zamknięcie okna nie usuwa rekordu natychmiast. Trwała historia kluczy przechowuje
identyfikatory i status, a nie sekrety. Treść odpowiedzi HTTP z błędami jest ukrywana.

Polityka VPN i brama kontrolują dostępne usługi. Uwierzytelnianie Odoo pozostaje
wymagane, a cofnięcie dostępu nie zamyka publicznej trasy Odoo. Dla niezależnych
sklonowanych środowisk użyj osobnego serwera Headscale i konfiguracji API, aby nie
zmieniać pierwotnej sieci.

## Wdrażanie usług w Oduflow

Użyj [przykładów konfiguracji usług](https://github.com/oduflow/oduflow-client-addons/tree/19.0-headscale/addons/oduscale/deploy)
jako punktu wyjścia. Zawierają wartości demonstracyjne: najpierw wybierz środowisko,
nazwy usług, publiczną domenę serwera sterującego, prefiksy VPN i domenę DNS.
Rzeczywiste wartości, argumenty narzędzi, wersje obrazów i wyniki zapisuj w
[dzienniku wdrożeń](https://github.com/oduflow/oduflow-client-addons/tree/19.0-headscale/log).
Dziennik zawiera historyczne obserwacje, a nie bieżący inwentarz środowisk.

1. Opublikuj wybraną gałąź Git i użyj `create_environment` z repozytorium,
   gałęzią, nazwą środowiska, `odoo_image="odoo:18.0"` i `template_name="none"`
   dla nowej bazy. W istniejącym środowisku zachowaj bazę danych.
   Upewnij się, że `/mnt/extra-addons/addons` jest na ścieżce dodatków. Użyj `pull_and_apply`
   z `install="oduscale"` przy pierwszej instalacji lub `upgrade="oduscale"`
   przy aktualizacji modułu. Włącz wątek cron w `.oduflow/odoo.conf`.
2. Wybierz i zapisz konkretne wersje obrazów Headscale i Tailscale. Utwórz cztery
   wolumeny przez `create_volume`: konfigurację Headscale, dane Headscale, stan
   bramy i konfigurację bramy. Dla niezależnych wdrożeń stosuj odrębne nazwy.
3. Dostosuj `addons/oduscale/deploy/headscale/config.yaml`: ustaw publiczny adres HTTPS serwera,
   prefiksy VPN i domenę MagicDNS. Dostosuj `addons/oduscale/deploy/headscale/policy.hujson`: użytkownik
   bramy jest właścicielem `tag:odoo`, a członkowie mają dostęp do tego tagu na porcie 80. Dostosuj
   `addons/oduscale/deploy/gateway/serve.json`, aby przekierować port 80 do kontenera Odoo na port 8069.
   Użyj `write_file_in_volume`, aby umieścić `config.yaml` i `policy.hujson` w katalogu
   głównym wolumenu konfiguracji Headscale oraz `serve.json` w katalogu głównym
   wolumenu konfiguracji bramy.
4. Użyj `create_service` dla Headscale z `command="serve"`. Zamontuj konfigurację
   pod `/etc/headscale:ro`, a dane pod `/var/lib/headscale`. Udostępnij tylko `/health`,
   `/key`, `/ts2021`, `/register`, `/auth`, `/oidc/callback`, `/verify` i
   `/machine/ping-response` na porcie 8080. Nie udostępniaj trasy ogólnej ani
   `/api/v1`. Odoo musi łączyć się z API przez wewnętrzną nazwę hosta usługi.
5. Przez `run_service_command` z `shell=false` utwórz użytkownika bramy, jeśli nie
   istnieje, wydaj klucz API, odczytaj listę użytkowników, aby uzyskać ID użytkownika bramy,
   i wydaj klucz wstępnej autoryzacji bramy z tagiem `tag:odoo`. Podstaw użytkownika i ID bramy:

   ```text
   headscale users create <gateway-user>
   headscale apikeys create --expiration 2160h
   headscale users list -o json
   headscale preauthkeys create --user <gateway-user-id> --expiration 1h --tags tag:odoo -o json
   ```

   Umieść klucz API w zmiennej środowiska Odoo `ODUSCALE_API_KEY` przez
   `update_environment`, zachowując pozostałe zmienne. Zapisz termin ważności, nigdy
   wartość. Przed wygaśnięciem wydaj nowy klucz, zmień zmienną, sprawdź
   **Test connection** i unieważnij stary klucz przez `headscale apikeys expire`.
6. Użyj `create_service` dla bramy Tailscale. Zamontuj stan pod `/var/lib/tailscale`,
   a konfigurację pod `/config:ro`. Demo używa `port=65535` bez nasłuchującego procesu,
   aby nie udostępniać przekierowania VPN publicznie. Ustaw poniższe zmienne,
   podstawiając jednorazowy klucz i publiczny adres serwera sterującego:

   ```text
   TS_AUTHKEY=<single-use-gateway-key>
   TS_AUTH_ONCE=true
   TS_STATE_DIR=/var/lib/tailscale
   TS_USERSPACE=true
   TS_HOSTNAME=odoo
   TS_EXTRA_ARGS=--login-server=<public-headscale-https-url> --accept-dns=false
   TS_SERVE_CONFIG=/config/serve.json
   ```

   Ten tryb użytkownika nie wymaga uprzywilejowanego kontenera, `NET_ADMIN` ani sieci hosta.
   Tagi pochodzą z klucza; nie dodawaj `--advertise-tags`. Po rejestracji usuń
   `TS_AUTHKEY` przez `update_service`, zachowując pozostałe ustawienia. Tożsamość
   bramy pozostaje w wolumenie stanu.
7. Skonfiguruj serwer Headscale w Odoo zgodnie z opisem powyżej: wewnętrzny API URL,
   publiczny Login URL i Odoo URL w VPN. Uruchom **Test connection**, a następnie według
   [podręcznika użytkownika](user_guide.md) podłącz tymczasowe urządzenie, zsynchronizuj je,
   otwórz Odoo przez VPN i sprawdź cofnięcie dostępu. Sprawdź, czy publiczny `/api/v1/user`
   jest niedostępny, a `/health` działa. Zapisz rzeczywiste wyniki i usuń testowe
   urządzenia oraz klucze. W razie potrzeby uruchom nieaktywne środowisko przez `start_environment`.

## Routing bramy i kopie zapasowe

Przykładowa brama przekazuje port TCP 80 przez szyfrowaną sieć VPN do portu Odoo
8069. Przy `workers=0` obejmuje to również ruch websocket. Wiele procesów roboczych
wymaga wewnętrznego proxy HTTP kierującego `/websocket` na port gevent.
Aby zapewnić dostęp wyłącznie przez VPN, przygotuj i sprawdź dostęp administratora
przez VPN przed zamknięciem publicznej trasy Odoo na proxy wejściowym.

Przykładowy Headscale używa SQLite z WAL w trwałym wolumenie danych;
nie wymaga osobnej usługi PostgreSQL. Twórz kopie SQLite przez API kopii zapasowych
lub przy zatrzymanym Headscale; zachowaj również klucze prywatne i konfigurację.
Twórz kopie stanu i konfiguracji bramy oraz bazy danych i magazynu plików Odoo.
Zapisuj odnośniki do kopii i kroki odtwarzania przed zmianami usług; nie umieszczaj
kluczy prywatnych ani danych dostępu do kopii w dzienniku. Dla niezależnych klonów
Odoo używaj osobnej instancji Headscale, aby nie zmieniały pierwotnej sieci VPN.

## Zgodność z Odoo 18

Do nowej instalacji na Odoo 18 użyj gałęzi `18.0`. Zainstaluj moduł z `addons` wraz z zadeklarowanymi zależnościami. Ta gałąź nie służy do obniżania wersji istniejącej bazy Odoo.
