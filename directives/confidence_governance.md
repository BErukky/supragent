# 📘 Confidence Governance Directive

This directive defines how **Super Signals** moderates confidence, suppresses unsafe timing, and communicates uncertainty — **without altering market structure truth or generating new signals**.

---

## Core Principle

> **Market Structure defines intent.**
> **Liquidity confirms intent.**
> **History provides humility.**
> **News controls permission.**
> **Confidence is earned, not assumed.**

This directive may **only reduce confidence or enforce WAIT states**. It must **never flip directional bias** or invalidate structural findings.

---

## Integration Point

This directive executes **after Layers 1–3** and **before final output (Layer 5)**.

```
Layer 1–3 → Base Confidence
Layer 4   → Risk & Uncertainty Scan
Governance→ Confidence Adjustment / Trade Suppression
Layer 5   → Human-Readable Output
```

---

## Governance Components

### 1️⃣ News Override Rules

**Objective:** Prevent high-confidence signals during periods of elevated external uncertainty.

#### Rules

| Impact | Action                    | Annotation                                             |
| ------ | ------------------------- | ------------------------------------------------------ |
| NONE   | No modification           | -                                                      |
| MEDIUM | Reduce confidence (-20)   | [!] News: Risk context detected (confidence moderated) |
| HIGH   | Enforce `WAIT / NO_TRADE` | [!] News: High-impact event imminent (Risk Override)   |

---

### 2️⃣ Numeric Confidence Modulation

- Base confidence is produced by Layers 1–3.
- Governance may **only subtract**, never add.
- If final confidence < 75 (for longs) or > 25 (for shorts) after adjustments -> Enforce `WAIT`.

---

### 3️⃣ Historical Assimilation (Sanity Check)

**Objective:** Prevent overconfidence in structurally valid but historically fragile conditions.

| Historical Context | Effect                  | Annotation                                         |
| ------------------ | ----------------------- | -------------------------------------------------- |
| Consistent Adverse | Reduce confidence (-15) | [~] History: Similar structures showed instability |
| Rare / unstable    | Flag uncertainty        | [~] History: Low data confidence in this structure |

---

## Final Governance Decision Logic

1. If HIGH news override present -> Enforce `WAIT`.
2. If final confidence < system threshold (75) -> Enforce `WAIT / NO_TRADE`.
3. Directional bias is only allowed if all safety checks pass.

> `WAIT` does **not** mean the market is wrong.
> It means **acting now is unsafe**.

---

**Instruction to Agent**: Your role is to be **honest under uncertainty**. When in doubt, reduce confidence and prefer WAIT.
