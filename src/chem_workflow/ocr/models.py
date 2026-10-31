"""Validated models for local experiment-record OCR drafts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReviewStatus = Literal["needs_review", "reviewed"]


class OCRField(BaseModel):
    """One extracted value plus enough provenance for human review."""

    value: str | None = None
    source_text: str | None = None
    status: ReviewStatus = "needs_review"
    warnings: list[str] = Field(default_factory=list)

    def display_value(self) -> str:
        """Return a safe UI string for a possibly missing value."""
        return self.value or ""


class OCRMaterial(BaseModel):
    """An extracted starting material or reagent."""

    name: OCRField = Field(default_factory=OCRField)
    amount: OCRField = Field(default_factory=OCRField)
    source_text: str | None = None
    status: ReviewStatus = "needs_review"

    def as_form_line(self) -> str:
        """Render the material in the existing ``name | amount`` UI format."""
        name = self.name.display_value()
        amount = self.amount.display_value()
        if name and amount:
            return f"{name} | {amount}"
        return name or amount


class OCRTableRow(BaseModel):
    """One row of the handwritten reagent table, kept as transcribed text."""

    name: str
    molar_mass: str | None = None
    equivalents: str | None = None
    amount: str | None = None
    mass: str | None = None
    volume: str | None = None
    density: str | None = None
    note: str | None = None
    source_text: str | None = None


class OCRRecordDraft(BaseModel):
    """Structured, review-required output from GLM-OCR."""

    status: Literal["draft"] = "draft"
    compound_id: OCRField = Field(default_factory=OCRField)
    product_name: OCRField = Field(default_factory=OCRField)
    smiles: OCRField = Field(default_factory=OCRField)
    starting_materials: list[OCRMaterial] = Field(default_factory=list)
    reagents: list[OCRMaterial] = Field(default_factory=list)
    # Reaction setup/addition notes that do not fit into the scalar condition fields.
    # Workup and purification remain separate so the generated record can format them.
    procedure: OCRField = Field(default_factory=OCRField)
    solvent: OCRField = Field(default_factory=OCRField)
    temperature: OCRField = Field(default_factory=OCRField)
    time: OCRField = Field(default_factory=OCRField)
    workup: OCRField = Field(default_factory=OCRField)
    purification: OCRField = Field(default_factory=OCRField)
    appearance: OCRField = Field(default_factory=OCRField)
    yield_mass: OCRField = Field(default_factory=OCRField)
    yield_percent: OCRField = Field(default_factory=OCRField)
    h1_nmr: OCRField = Field(default_factory=OCRField)
    c13_nmr: OCRField = Field(default_factory=OCRField)
    hrms: OCRField = Field(default_factory=OCRField)
    ms: OCRField = Field(default_factory=OCRField)
    ir: OCRField = Field(default_factory=OCRField)
    uv: OCRField = Field(default_factory=OCRField)
    # Parsed reagent table used for stoichiometry checks and review display.
    material_table: list[OCRTableRow] = Field(default_factory=list)
    raw_text: str = ""
    unmapped_text: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    page_count: int = 1

    def scalar_fields(self) -> dict[str, OCRField]:
        """Return scalar fields in stable display order."""
        return {
            name: getattr(self, name)
            for name in (
                "compound_id",
                "product_name",
                "smiles",
                "procedure",
                "solvent",
                "temperature",
                "time",
                "workup",
                "purification",
                "appearance",
                "yield_mass",
                "yield_percent",
                "h1_nmr",
                "c13_nmr",
                "hrms",
                "ms",
                "ir",
                "uv",
            )
        }

    def form_values(self) -> dict[str, str]:
        """Map this draft into the existing experiment-record form keys."""
        return {
            "compound_id": self.compound_id.display_value(),
            "product_name": self.product_name.display_value(),
            "compound_smiles": self.smiles.display_value(),
            "procedure": self.procedure.display_value(),
            "starting_materials": "\n".join(
                line for line in (item.as_form_line() for item in self.starting_materials) if line
            ),
            "reagents": "\n".join(
                line for line in (item.as_form_line() for item in self.reagents) if line
            ),
            "solvent": self.solvent.display_value(),
            "temperature": self.temperature.display_value(),
            "reaction_time": self.time.display_value(),
            "workup": self.workup.display_value(),
            "purification": self.purification.display_value(),
            "appearance": self.appearance.display_value(),
            "yield_mass": self.yield_mass.display_value(),
            "yield_percent": self.yield_percent.display_value(),
            "nmr_1h_text": self.h1_nmr.display_value(),
            "nmr_13c_text": self.c13_nmr.display_value(),
            "hrms_text": self.hrms.display_value(),
            "ms_text": self.ms.display_value(),
            "ir_text": self.ir.display_value(),
            "uv_text": self.uv.display_value(),
            "other_characterization": "\n".join(self.unmapped_text),
        }


class OCRServiceStatus(BaseModel):
    """User-facing status returned by the WSL runtime manager."""

    state: Literal["ready", "starting", "stopped", "error"]
    message: str
    endpoint: str | None = None
    model: str | None = None
    details: list[str] = Field(default_factory=list)


__all__ = [
    "OCRField",
    "OCRMaterial",
    "OCRRecordDraft",
    "OCRServiceStatus",
    "OCRTableRow",
    "ReviewStatus",
]
