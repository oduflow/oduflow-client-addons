<!-- i18n source=user_guide.md sha=d4949a47f9c9 lang=pl -->
# Podręcznik użytkownika Oduscale

Oduscale pozwala osobom zarządzającym dostępem podłączać urządzenia pracowników do
firmowej sieci VPN przez Headscale i Tailscale. Połączenie VPN i uprawnienia Odoo są
niezależne: pracownicy nadal potrzebują własnego konta Odoo i muszą się zalogować.

## Zanim zaczniesz

Administrator musi skonfigurować serwer Headscale i przyznać Ci uprawnienie **Oduscale / Manage
employee VPN access**. Pracownik i jego powiązany użytkownik Odoo, jeśli istnieje,
muszą być aktywni. Pracownik instaluje Tailscale na każdym urządzeniu. Polityka VPN
i brama określają usługi dostępne z danego urządzenia.

## Przyznawanie dostępu i podłączanie urządzenia

1. Otwórz **Oduscale → Employee Access** i utwórz rekord dla pracownika i serwera.
   Rekordy dostępu są również dostępne na karcie **Oduscale** w formularzu pracownika.
2. Zapisz rekord i kliknij **Grant access**. Stan zmieni się na **Active**.
3. Kliknij **Connect a device**, aby wydać jednorazowy klucz i wyświetlić polecenie połączenia.
   Domyślna ważność klucza to 60 minut; okno pokazuje termin wygaśnięcia.
4. Przekaż polecenie bezpiecznie wyłącznie temu pracownikowi. Zawiera sekret.
   Pracownik uruchamia je na swoim urządzeniu w terminalu z uprawnieniami administratora.
5. Po połączeniu otwórz adres Odoo w sieci VPN wskazany w rekordzie dostępu i zaloguj
   się kontem Odoo pracownika.
6. Kliknij **Synchronize**, aby natychmiast odświeżyć listę urządzeń. Powtórz **Connect a
   device** dla każdego kolejnego urządzenia: każde wymaga nowego klucza.

Stan **Active** oznacza przyznany dostęp, a nie potwierdzenie połączenia urządzenia.
Dla pracownika na danym serwerze może istnieć tylko jeden rekord dostępu. Po powiązaniu
z Headscale rekordu nie można przypisać ponownie ani usunąć; zachowaj go do audytu
i cofnij dostęp, gdy nie jest już potrzebny.

## Przeglądanie urządzeń i historii rejestracji

- Otwórz **Devices** w rekordzie dostępu lub **Oduscale → Devices**, aby zobaczyć inwentarz.
  Sprawdź adresy VPN, stan online, obecność i czas ostatniej aktywności. Rekord dostępu
  udostępnia również opcjonalną kolumnę terminu wygaśnięcia urządzenia.
- Urządzenie oznaczone jako nieobecne pozostaje w historii, ale nie jest już znajdowane w Headscale.
  Stan online pochodzi z ostatniej synchronizacji, a nie z bieżącego testu połączenia.
- **Enrollment history** pokazuje identyfikatory kluczy, czas utworzenia i wygaśnięcia
  oraz znaczniki użycia i cofnięcia. Nie przechowuje polecenia połączenia ani sekretu klucza.
- Synchronizacja jest zaplanowana co 5 minut. **Synchronize** odświeża jeden rekord
  dostępu; ten sam przycisk na serwerze odświeża jego połączenia.

## Cofanie dostępu

- W **Enrollment history** kliknij **Expire**, aby unieważnić klucz rejestracji.
  Wygaśnięcie klucza nie rozłącza urządzenia, które już się nim zarejestrowało.
- W **Devices** kliknij **Revoke** i potwierdź usunięcie jednego urządzenia z Headscale.
  Pozostałe urządzenia i klucze rejestracji pozostają bez zmian.
- Kliknij **Revoke all access** w rekordzie dostępu i potwierdź unieważnienie wszystkich
  kluczy oraz usunięcie wszystkich urządzeń powiązanego użytkownika Headscale pracownika.
  Rekord otrzyma stan **Revoked**; zdalny użytkownik i lokalna historia pozostaną.
- Aby przywrócić dostęp, kliknij **Grant access**, następnie **Connect a device** i użyj nowego klucza.

Archiwizacja pracownika lub jego powiązanego użytkownika Odoo automatycznie cofa
aktywny dostęp VPN. Jeśli Headscale nie może potwierdzić cofnięcia, archiwizacja
kończy się błędem; skontaktuj się z administratorem i ponów ją po przywróceniu usługi.

## Rozwiązywanie problemów z połączeniem

- Jeśli klucz wygasł lub został już użyty, uzyskaj nowy przez **Connect a device**.
- Jeśli urządzenia nie ma w inwentarzu, kliknij **Synchronize** i sprawdź, czy pracownik
  pomyślnie wykonał polecenie połączenia.
- Jeśli VPN działa, ale Odoo się nie otwiera, poproś administratora o sprawdzenie
  polityki VPN, bramy i skonfigurowanego adresu Odoo. Osobno sprawdź dane logowania Odoo.
- Jeśli działanie zgłasza błąd Headscale, nie zakładaj, że zostało zakończone. Poproś
  administratora o przywrócenie łączności, a potem ponów działanie i synchronizację.

Cofnięcie dostępu VPN nie blokuje osobno udostępnionego publicznego adresu Odoo.

## Zgodność z Odoo 17

Do nowej instalacji na Odoo 17 użyj gałęzi `17.0`. Zainstaluj moduł z `addons` wraz z zadeklarowanymi zależnościami. Ta gałąź nie służy do obniżania wersji istniejącej bazy Odoo.
