"""Experiment record data models and Markdown rendering."""

from __future__ import annotations

from collections.abc import Iterable

from chem_workflow.records.models import (
    Characterization,
    Language,
    Material,
    ReactionRecord,
    RecordInputError,
    YieldInfo,
)

_EN_TEMPLATE = """# {title}

{compound_paragraph}

{procedure_paragraph}

## Characterization

{characterization_section}
"""

_ZH_TEMPLATE = """# {title}

{compound_paragraph}

{procedure_paragraph}

## 表征数据

{characterization_section}
"""


def render_experiment_record(record: ReactionRecord, language: Language = "en") -> str:
    """Render a `ReactionRecord` as Markdown."""
    if language == "en":
        template = _EN_TEMPLATE
        context = _build_english_context(record)
    elif language == "zh":
        template = _ZH_TEMPLATE
        context = _build_chinese_context(record)
    else:
        raise RecordInputError(f"不支持的记录语言：{language!r}；当前支持 en / zh")
    return _compact_markdown(template.format(**context))


def _build_english_context(record: ReactionRecord) -> dict[str, str]:
    return {
        "title": _english_title(record),
        "compound_paragraph": _english_compound_paragraph(record),
        "procedure_paragraph": _english_procedure_paragraph(record),
        "characterization_section": _characterization_section(record.characterization),
    }


def _build_chinese_context(record: ReactionRecord) -> dict[str, str]:
    return {
        "title": _chinese_title(record),
        "compound_paragraph": _chinese_compound_paragraph(record),
        "procedure_paragraph": _chinese_procedure_paragraph(record),
        "characterization_section": _characterization_section(record.characterization),
    }


def _english_title(record: ReactionRecord) -> str:
    if record.product_name:
        return f"Compound {record.compound_id}: {record.product_name}"
    return f"Compound {record.compound_id}"


def _chinese_title(record: ReactionRecord) -> str:
    if record.product_name:
        return f"化合物 {record.compound_id}：{record.product_name}"
    return f"化合物 {record.compound_id}"


def _english_compound_paragraph(record: ReactionRecord) -> str:
    subject = f"Compound {record.compound_id}"
    if record.product_name:
        subject += f" ({record.product_name})"
    if record.appearance:
        return f"{subject} was obtained as {_english_appearance(record.appearance)}."
    return f"{subject} was obtained."


def _chinese_compound_paragraph(record: ReactionRecord) -> str:
    subject = f"化合物 {record.compound_id}"
    if record.product_name:
        subject += f"（{record.product_name}）"
    if record.appearance:
        return f"{subject}为{record.appearance}。"
    return f"获得{subject}。"


def _english_procedure_paragraph(record: ReactionRecord) -> str:
    sentences: list[str] = []
    reaction = record.reaction
    starting_materials = _join_materials(reaction.starting_materials, language="en")
    reagents = _join_materials(reaction.reagents, language="en")

    if starting_materials and reagents:
        solvent = f" in {reaction.solvent}" if reaction.solvent else ""
        sentences.append(f"To a solution of {starting_materials}{solvent} was added {reagents}.")
    elif starting_materials:
        solvent = f" in {reaction.solvent}" if reaction.solvent else ""
        sentences.append(f"A solution of {starting_materials}{solvent} was prepared.")
    elif reagents:
        sentences.append(f"The reaction was set up with {reagents}.")

    condition = _english_condition(reaction.temperature, reaction.time)
    if condition:
        sentences.append(f"The reaction mixture was stirred {condition}.")
    if record.workup:
        sentences.append(f"The mixture was {record.workup}.")

    final_sentence = _english_final_sentence(record)
    if final_sentence:
        sentences.append(final_sentence)

    if not sentences:
        return "Experimental procedure was not specified."
    return " ".join(sentences)


def _chinese_procedure_paragraph(record: ReactionRecord) -> str:
    sentences: list[str] = []
    reaction = record.reaction
    starting_materials = _join_materials(reaction.starting_materials, language="zh")
    reagents = _join_materials(reaction.reagents, language="zh")

    if starting_materials and reagents:
        solvent = f"溶于{reaction.solvent}" if reaction.solvent else ""
        sentences.append(f"将{starting_materials}{solvent}，加入{reagents}。")
    elif starting_materials:
        solvent = f"溶于{reaction.solvent}" if reaction.solvent else ""
        sentences.append(f"将{starting_materials}{solvent}。")
    elif reagents:
        sentences.append(f"反应中使用{reagents}。")

    condition = _chinese_condition(reaction.temperature, reaction.time)
    if condition:
        sentences.append(f"反应液{condition}。")
    if record.workup:
        sentences.append(f"反应混合物经{record.workup}。")

    final_sentence = _chinese_final_sentence(record)
    if final_sentence:
        sentences.append(final_sentence)

    if not sentences:
        return "实验步骤暂未提供。"
    return "".join(sentences)


def _english_condition(temperature: str | None, time: str | None) -> str:
    if temperature and time:
        return f"at {temperature} for {time}"
    if temperature:
        return f"at {temperature}"
    if time:
        return f"for {time}"
    return ""


def _chinese_condition(temperature: str | None, time: str | None) -> str:
    if temperature and time:
        return f"在{temperature}下搅拌{time}"
    if temperature:
        return f"在{temperature}下搅拌"
    if time:
        return f"搅拌{time}"
    return ""


def _english_final_sentence(record: ReactionRecord) -> str:
    product = record.product_name or f"compound {record.compound_id}"
    yield_text = _yield_text(record.yield_)
    if record.purification and yield_text:
        return (
            f"The crude product was purified by {record.purification} "
            f"to afford {product} ({yield_text})."
        )
    if record.purification:
        return f"The crude product was purified by {record.purification} to afford {product}."
    if yield_text:
        return f"{product} was obtained ({yield_text})."
    return ""


def _chinese_final_sentence(record: ReactionRecord) -> str:
    product = record.product_name or f"化合物 {record.compound_id}"
    yield_text = _yield_text(record.yield_)
    if record.purification and yield_text:
        return f"粗产物经{record.purification}纯化，得到{product}（{yield_text}）。"
    if record.purification:
        return f"粗产物经{record.purification}纯化，得到{product}。"
    if yield_text:
        return f"得到{product}（{yield_text}）。"
    return ""


def _join_materials(materials: Iterable[Material], language: Language) -> str:
    rendered = [_format_material(material) for material in materials]
    if language == "zh":
        return _join_chinese(rendered)
    return _join_english(rendered)


def _format_material(material: Material) -> str:
    if material.amount:
        return f"{material.name} ({material.amount})"
    return material.name


def _join_english(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _join_chinese(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} 和 {items[1]}"
    return "、".join(items[:-1]) + f"和{items[-1]}"


def _english_appearance(value: str) -> str:
    normalized = value.strip()
    if normalized.lower().startswith(("a ", "an ", "the ")):
        return normalized
    article = "an" if normalized[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {normalized}"


def _yield_text(yield_info: YieldInfo | None) -> str:
    if yield_info is None:
        return ""
    values = [value for value in (yield_info.mass, yield_info.percent) if value]
    return ", ".join(values)


def _characterization_section(characterization: Characterization) -> str:
    lines: list[str] = []
    labeled_fields = [
        ("1H NMR", characterization.h1_nmr),
        ("13C NMR", characterization.c13_nmr),
        ("HRMS", characterization.hrms),
        ("MS", characterization.ms),
        ("IR", characterization.ir),
        ("UV-vis", characterization.uv),
    ]
    for label, value in labeled_fields:
        if value:
            lines.append(_ensure_label(value, label))
    lines.extend(item for item in characterization.other if item)
    if not lines:
        return "Not provided."
    return "\n\n".join(lines)


def _ensure_label(value: str, label: str) -> str:
    stripped = value.strip()
    if stripped.lower().startswith(label.lower()):
        return stripped
    return f"{label} {stripped}"


def _compact_markdown(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines)
