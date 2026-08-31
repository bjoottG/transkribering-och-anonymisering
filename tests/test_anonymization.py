"""Tester för regexdetektering, pseudonymisering, genitiv och kodnyckel. NER mockas."""
from __future__ import annotations

from app.anonymization import Anonymizer


def _anonymizer(fake_ner=None) -> Anonymizer:
    return Anonymizer(ner=fake_ner or (lambda text: []))


class TestRegexDetection:
    def test_personnummer_12_siffror(self):
        result = _anonymizer().anonymize("Personnummer: 19850312-1234.")
        assert "19850312-1234" not in result
        assert "[Personnummer 1]" in result

    def test_personnummer_10_siffror(self):
        result = _anonymizer().anonymize("Pnr 850312-1234 gäller.")
        assert "850312-1234" not in result
        assert "[Personnummer 1]" in result

    def test_personnummer_plus_separator(self):
        assert "[Personnummer 1]" in _anonymizer().anonymize("Äldre: 250312+5678.")

    def test_telefonnummer_mobil(self):
        result = _anonymizer().anonymize("Ring 070-123 45 67 i morgon.")
        assert "070-123 45 67" not in result
        assert "[Telefon 1]" in result

    def test_telefonnummer_landskod(self):
        result = _anonymizer().anonymize("Nås på +46 70 123 45 67.")
        assert "[Telefon 1]" in result

    def test_epost(self):
        result = _anonymizer().anonymize("Mejla anna.andersson@example.se snarast.")
        assert "anna.andersson@example.se" not in result
        assert "[E-post 1]" in result

    def test_registreringsnummer(self):
        result = _anonymizer().anonymize("Bilen ABC 123 stod parkerad.")
        assert "ABC 123" not in result
        assert "[Registreringsnummer 1]" in result

    def test_vanlig_text_lamnas_ifred(self):
        text = "Vi möttes klockan 14 den 3 mars 2024 och åt lunch."
        assert _anonymizer().anonymize(text) == text


class TestPseudonymisering:
    def test_samma_entitet_far_samma_pseudonym(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        first = anonymizer.anonymize("Anna Andersson kom först. Sedan pratade Anna Andersson igen.")
        assert first.count("[Person 1]") == 2

    def test_konsekvent_over_flera_anrop(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        assert "[Person 1]" in anonymizer.anonymize("Anna Andersson inledde.")
        assert "[Person 1]" in anonymizer.anonymize("Anna Andersson avslutade.")

    def test_olika_entiteter_far_olika_nummer(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        result = anonymizer.anonymize("Anna Andersson träffade Björn Otterberg i Härnösand.")
        assert "[Person 1]" in result and "[Person 2]" in result and "[Plats 1]" in result

    def test_case_insensitiv_matchning(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        anonymizer.anonymize("Härnösand är fint.")
        result = anonymizer.anonymize("Vi åkte till HÄRNÖSAND igen.")
        assert "HÄRNÖSAND" not in result and "[Plats 1]" in result

    def test_genitiv_s(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        result = anonymizer.anonymize("Anna kom in. Annas väska stod kvar.")
        assert "[Person 1]" in result
        assert "[Person 1]s väska" in result
        assert "Annas" not in result

    def test_genitiv_forst_grundform_sedan(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        anonymizer.anonymize("Annas väska.")
        result = anonymizer.anonymize("Anna hämtade den.")
        assert "[Person 1]" in result
        entries = anonymizer.codebook()
        assert entries[0].original == "Anna"

    def test_kand_entitet_fangas_utan_ner_traff(self, fake_ner):
        """Andra svepningen: entitet som NER hittat tidigare ersätts även där NER missar."""
        anonymizer = Anonymizer(ner=fake_ner)
        anonymizer.anonymize("Tillväxtverket är en myndighet.")
        # NER-mocken träffar inte gemener — men svepningen ska ändå ersätta
        result = anonymizer.anonymize("Rapporten från tillväxtverket kom.")
        assert "[Organisation 1]" in result

    def test_ner_typer_kan_begransas(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner, entity_types=("PER",))
        result = anonymizer.anonymize("Anna Andersson besökte Härnösand.")
        assert "[Person 1]" in result and "Härnösand" in result

    def test_lag_score_ignoreras(self):
        def ner(text):
            return [{"entity_group": "PER", "word": "Osäker", "start": 0, "end": 6, "score": 0.30}]
        result = Anonymizer(ner=ner).anonymize("Osäker träff i texten.")
        assert "Osäker" in result


class TestKodnyckel:
    def test_kodnyckel_innehall_och_antal(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        anonymizer.anonymize(
            "Anna Andersson (19850312-1234) bor i Härnösand. Anna Andersson trivs i Härnösand."
        )
        entries = {e.pseudonym: e for e in anonymizer.codebook()}
        assert entries["[Person 1]"].original == "Anna Andersson"
        assert entries["[Person 1]"].type_label == "Person"
        assert entries["[Person 1]"].count == 2
        assert entries["[Plats 1]"].count == 2
        assert entries["[Personnummer 1]"].original == "19850312-1234"

    def test_tom_kodnyckel(self):
        assert _anonymizer().codebook() == []

    def test_sortering_per_typ(self, fake_ner):
        anonymizer = Anonymizer(ner=fake_ner)
        anonymizer.anonymize("I Härnösand bor Anna Andersson och Björn Otterberg.")
        pseudonyms = [e.pseudonym for e in anonymizer.codebook()]
        assert pseudonyms == ["[Person 1]", "[Person 2]", "[Plats 1]"]
