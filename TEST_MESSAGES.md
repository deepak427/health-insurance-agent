# Test Messages for HIP Agent

Run these messages in sequence to test the updated prompt and edge case handling.

---

## 1. Basic FAQ (sanity check)
```
What is a deductible?
```
**Expected:** Quick definition from FAQ tool, no errors.

---

## 2. Claim filing (tool usage check)
```
How do I file an auto insurance claim?
```
**Expected:** Step-by-step guide with required documents.

---

## 3. PDF generation (artifact check)
```
Generate a PDF guide on life insurance for my client
```
**Expected:** Single response saying "guide is ready and attached" — no mention of filename or "artifact".

---

## 4. Policy comparison — missing member details (should ask upfront)
```
Compare Star Health Comprehensive and HDFC ERGO Optima Secure
```
**Expected:** Agent asks for age, adults, children, and sum insured in ONE message before proceeding.

---

## 5. Policy comparison — full details (happy path)
```
Compare Star Health Comprehensive and HDFC ERGO Optima Secure for 2 adults, age 35, sum insured 5 lakh, 0 children
```
**Expected:** 
- Agent searches both policies
- Calculates premiums
- Generates comparison PDF
- ONE response: "comparison is ready and attached"

---

## 6. Policy comparison — one policy not found (should suggest alternatives)
```
Compare Star Health Comprehensive and XYZ NonExistent Policy for 2 adults, age 35, sum insured 5 lakh
```
**Expected:** ONE message total saying XYZ isn't available, suggests alternatives like Star Health Family Health Optima, HDFC ERGO My:health Suraksha, Niva Bupa ReAssure. Asks if user wants to try one of those.

---

## 7. Policy comparison — premium calculation fails (the bug scenario)
```
Compare Activ Care and Activ Health for 2 adults, age 35, sum insured 5 lakh, 0 children
```
**Expected:** 
- **ONE message total** (not two!)
- Says live quotes aren't available for these policies right now (paraphrased, not raw API errors)
- Suggests alternatives: Star Health Comprehensive, HDFC ERGO Optima Secure, Niva Bupa ReAssure, etc.
- Does NOT attempt to generate PDF

---

## 8. Estimate premium (non-comparison flow)
```
Estimate health insurance premium for age 30, coverage 10 lakh
```
**Expected:** Quick rough estimate using estimate_premium tool (not the live comparison flow).

---

## 9. Document analysis (upload test)
*Upload a PDF insurance document first, then send:*
```
Analyze this policy document
```
**Expected:** Agent reads the uploaded document and summarizes key coverage details.

---

## 10. Edge case — ambiguous policy name
```
Compare Star and HDFC for 2 adults, age 40, sum insured 10 lakh
```
**Expected:** Agent finds multiple matches for "Star" (Star Comprehensive, Star Family Health Optima, etc.) and asks user to clarify which one in ONE message.

---

## Notes
- Test #7 is the **critical one** — it reproduces the double message bug you reported
- After the prompt fix, you should see ONE message instead of two, with friendly error handling
- The suggested policies list (Star Health Comprehensive, HDFC ERGO Optima Secure, etc.) assumes these have working premium APIs on your backend — adjust if needed
