<!-- i18n source=user_guide.md sha=a22cbfc9842b lang=pl -->
# Podręcznik użytkownika OduLogin

OduLogin pomaga administratorowi odtworzyć widok użytkownika wewnętrznego bez
proszenia o hasło tego użytkownika.

## Przełączanie z górnego paska

1. Zaloguj się na konto z uprawnieniami administratora Ustawień.
2. Wybierz **Przełącz użytkownika** na górnym pasku.
3. Wybierz aktywnego użytkownika wewnętrznego i kliknij **Przełącz użytkownika**.
4. Odoo ponownie wczyta bieżący adres URL jako wybrany użytkownik. Od tej chwili
   obowiązują jego zwykłe reguły dostępu, dlatego bieżący ekran może wyświetlić
   błąd dostępu.

## Przełączanie z rekordu użytkownika

1. Otwórz **Ustawienia > Użytkownicy i firmy > Użytkownicy** i wybierz użytkownika.
2. Otwórz menu **Akcje** i wybierz **Przełącz użytkownika**.
3. Potwierdź w oknie wstępnie wybranego użytkownika.

## Powrót do konta administratora

Wybierz **Wróć do administratora** na górnym pasku. Odoo ponownie wczyta ten sam
adres URL z kontem pierwotnego administratora.

W jednej sesji przeglądarki może być aktywne tylko jedno przełączenie. Przed
wybraniem kolejnego użytkownika wróć do konta administratora. Nie można wybrać
użytkowników portalu, użytkowników nieaktywnych, bieżącego administratora ani
superużytkownika technicznego.

## Zgodność z Odoo 16

Do nowej instalacji na Odoo 16 użyj gałęzi `16.0`. Zainstaluj moduł z `addons` wraz z zadeklarowanymi zależnościami. Ta gałąź nie służy do obniżania wersji istniejącej bazy Odoo.
