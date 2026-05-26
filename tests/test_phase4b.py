"""Phase 4b tests: .dcm/.nii ingestion, blob storage, and DICOM de-identification.

Synthetic files are generated in-test (no binaries committed), proving real
imaging files flow through the adapter the same way your TCIA/OpenNeuro files will.
"""
from io import BytesIO
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from domain.models.base import SourceSystem
from domain.models.imaging_study import ImageFormat, Modality
from ingestion.blob_store import FilesystemBlobStore
from ingestion.imaging_adapter import ImagingFileAdapter


def _make_dicom(path: Path, mrn: str) -> None:
    ds = Dataset()
    ds.PatientName = "Doe^Jane"
    ds.PatientID = mrn
    ds.PatientBirthDate = "19800101"
    ds.Modality = "CT"
    ds.StudyDate = "20260411"
    ds.BodyPartExamined = "CHEST"
    ds.SeriesNumber = 2
    ds.Rows = 2
    ds.Columns = 2
    ds.BitsAllocated = 8
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = bytes([0, 1, 2, 3])
    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = CTImageStorage
    fm.MediaStorageSOPInstanceUID = generate_uid()
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = generate_uid()
    ds.file_meta = fm
    ds.save_as(str(path), enforce_file_format=True)


def _make_nifti(path: Path) -> None:
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.int16), np.eye(4)), str(path))


def test_blob_store_round_trip(tmp_path):
    store = FilesystemBlobStore(tmp_path / "blobs")
    uri = store.put("a/b.bin", b"hello")
    assert uri.startswith("file://")
    assert store.get(uri) == b"hello"


def test_dicom_ingest_extracts_metadata_and_deidentifies(tmp_path):
    dcm = tmp_path / "scan.dcm"
    _make_dicom(dcm, "1001")
    store = FilesystemBlobStore(tmp_path / "blobs")

    studies = list(
        ImagingFileAdapter([(dcm, "1001")], {"1001": "canon-1"}, store).read()
    )
    assert len(studies) == 1
    s = studies[0]
    assert s.patient_id == "canon-1"
    assert s.modality is Modality.CT
    assert s.body_part == "CHEST"
    assert s.series_count == 2
    assert s.source_format is ImageFormat.DICOM
    assert s.source_system is SourceSystem.PACS

    # the stored blob must be PHI-free
    stored = pydicom.dcmread(BytesIO(store.get(s.image_uri)))
    assert str(stored.get("PatientName", "")) == ""
    assert str(stored.get("PatientID", "")) == ""


def test_nifti_ingest_lowers_quality_for_assumed_metadata(tmp_path):
    nii = tmp_path / "brain.nii"
    _make_nifti(nii)
    store = FilesystemBlobStore(tmp_path / "blobs")

    studies = list(
        ImagingFileAdapter([(nii, "2002")], {"2002": "canon-2"}, store).read()
    )
    assert len(studies) == 1
    s = studies[0]
    assert s.source_format is ImageFormat.NIFTI
    assert s.modality is Modality.MR  # assumed
    assert s.data_quality_score < 1.0  # flagged because metadata is assumed
    assert store.get(s.image_uri)  # bytes were stored


def test_unknown_mrn_skipped(tmp_path):
    dcm = tmp_path / "scan.dcm"
    _make_dicom(dcm, "9999")
    studies = list(
        ImagingFileAdapter([(dcm, "9999")], {"1001": "canon-1"},
                           FilesystemBlobStore(tmp_path / "blobs")).read()
    )
    assert studies == []
