# Slice 03: Student profiles

## Goal

Allow each authenticated student to maintain an incomplete but structured academic profile that future matching and AI assistant features can use without guessing eligibility from missing data.

## Acceptance criteria

- Authenticated users can create, read, and update only their own profile.
- Missing fields are allowed and surfaced through completeness metadata.
- Academic scores and test scores are validated.
- Invalid combinations, such as IELTS scores without a taken English test, are rejected.
- The database enforces core numeric constraints.
- Tests cover profile creation, update, validation, missing-profile behavior, and data isolation.

## Known limitations

- The profile is not yet connected to opportunity matching.
- Profile deletion and export will be added with the privacy/account-management slice.
- The profile is stored as normalized core fields plus JSON lists; later matching may split some fields into separate tables if needed.
