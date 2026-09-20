<!-- i18n source=admin_guide.md sha=4b27909ea7fa lang=pl -->
# Podręcznik administratora OduLogin

## Instalacja i dostęp

Zainstaluj **OduLogin** z poziomu Aplikacji. Moduł nie ma menu konfiguracji.
Elementy sterujące przełączaniem są dostępne wyłącznie dla użytkowników w
`base.group_system`, czyli standardowej grupie administratorów Ustawień.

Można wybierać wyłącznie aktywnych użytkowników wewnętrznych. OduLogin celowo
wyklucza użytkowników portalu i superużytkownika technicznego, ponieważ element
powrotu jest komponentem panelu systemowego backendu, a podszycie się pod konto
techniczne przekraczałoby granicę uprawnień.

## Bezpieczeństwo i eksploatacja

Identyfikator pierwotnego administratora jest przechowywany wyłącznie w
sesji Odoo po stronie serwera. Rozpoczęcie lub zakończenie przełączenia aktualizuje
identyfikator użytkownika sesji, login, kontekst i token sesji, a następnie
zmienia identyfikator sesji i ponownie wczytuje bieżący adres URL. Zagnieżdżone
przełączanie jest blokowane.

Działania wykonane po przełączeniu są przypisywane wybranemu użytkownikowi.
Używaj tej funkcji do wsparcia i diagnozowania dostępu, szybko wracaj do konta
administratora i nie używaj jej do ukrywania rzeczywistego operatora. OduLogin
nie dodaje osobnego trwałego modelu audytowego; zachowuj standardowe logi Odoo i
reverse proxy zgodnie z polityką audytu.

Odebranie uprawnień administratora Ustawień podczas aktywnego przełączenia nie
uniemożliwia pierwotnemu operatorowi powrotu do własnego aktywnego konta. Jeśli
to konto zostanie dezaktywowane, próba powrotu zostanie odrzucona i operator
musi się wylogować oraz uwierzytelnić za pomocą innego konta.

## Zgodność z Odoo 18

Do nowej instalacji na Odoo 18 użyj gałęzi `18.0`. Zainstaluj moduł z `addons` wraz z zadeklarowanymi zależnościami. Ta gałąź nie służy do obniżania wersji istniejącej bazy Odoo.
