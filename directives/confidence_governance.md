# 📘 Confidence Governance Directive (v2.1)

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

## 1️⃣ Proportional Modulation (v2.1 Upgrade)

**Objective:** Prevent confidence collapses from "minor" news while maintaining a strict ceiling on risk.

#### The Scaling Formula

Base confidence is produced by Layers 1–3. Governance then applies the following scaling:
`FinalConfidence = BaseConfidence * (1 - RiskPenalty / 100)`

- **Penalty 0-35 (NORMAL)**: Negligible impact on confidence.
- **Penalty 36-75 (CAUTION)**: Scales confidence down proportionally. Allows trades if chart strength is extremely high.
- **Penalty >75 (CRITICAL)**: Mandatory `WAIT / LOCKED` state.

---

## 2️⃣ Governance Lock Rules

### 🚨 Protocol Hard Lock

**Any** news event classified as `protocol` (Chain halt, consensus bug, validator failure) originating from a **Trusted Source** (Trust >= 0.8) triggers an automatic **CRITICAL LOCK**.

- **Technical signals are ignored**.
- **Action is forced to WAIT**.

### 📉 Verification Hold (`WAIT_VERIFICATION`)

Triggered when a significant penalty (>= 15) is detected from a single, low-trust aggregator without consensus from independent domains.

- **Hold Duration**: Until consensus is reached or risk decays.

---

## 3️⃣ Threshold Logic

- **Actionable Signal**: Bias is only allowed if `FinalConfidence >= 70`.
- **System Default**: If `FinalConfidence < 70`, enforce `WAIT / NO_TRADE`.

---

**Instruction to Agent**: Your role is to be **honest under uncertainty**. When in doubt, prefer WAIT. v2.1 allows for more nuance, but safety remains the priority.
