"""Phase 2 ingestion tests: the CSV adapter produces correct, provenance-tagged
Patient objects, normalizes messy fields, and skips rows it can't validate.
"""
from datetime import date
from pathlib import Path

from domain.models.base import SourceSystem
from domain.models.patient import Patient, Sex
from ingestion.csv_adapter import CSVPatientAdapter

SAMPLE = Path(__file__).parent.parent / "ingestion" / "sample_data" / "patients.csv"


def test_reads_all_rows():
    patients = list(CSVPatientAdapter(SAMPLE).read())
    assert len(patients) == 6
    assert all(isinstance(p, Patient) for p in patients)


def test_normalizes_dates_and_sex():
    by_mrn = {p.mrn: p for p in CSVPatientAdapter(SAMPLE).read()}
    turing = by_mrn["MRN-2002"]
    assert turing.birth_date == date(1912, 6, 23)  # US m/d/Y coerced to ISO
    assert turing.sex is Sex.MALE
    assert by_mrn["1001"].sex is Sex.FEMALE  # "F" normalized
    assert by_mrn["3003"].birth_date == date(1906, 12, 9)


def test_sets_provenance_and_canonical_id():
    p = next(CSVPatientAdapter(SAMPLE).read())
    assert p.source_system is SourceSystem.CSV_UPLOAD
    assert p.id != p.source_record_id  # canonical UUID distinct from source id
    assert p.source_record_id == p.mrn


def test_coercion_lowers_quality_score():
    by_mrn = {p.mrn: p for p in CSVPatientAdapter(SAMPLE).read()}
    # Turing: m/d/Y date coercion + "N/A" deceased coercion -> below 1.0
    assert by_mrn["MRN-2002"].data_quality_score < 1.0


def test_unparseable_dob_row_is_skipped(tmp_path):
    csv_text = (
        "patient_id,first_name,last_name,dob,gender,deceased\n"
        "9001,No,Date,not-a-date,M,false\n"
        "9002,Good,Row,1990-01-01,F,false\n"
    )
    path = tmp_path / "x.csv"
    path.write_text(csv_text)
    patients = list(CSVPatientAdapter(path).read())
    assert len(patients) == 1
    assert patients[0].mrn == "9002"
