# Farmer Value Ladder
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Purpose:** Define what value farmers receive at each participation level, ensuring value delivery BEFORE data extraction.

---

## Core Principle

> **The farmer must receive value BEFORE being asked for data.**  
> Every data request must be justified by a tangible farmer benefit that has already been delivered or is immediately visible.

---

## The Value Ladder

### Level 0: Install Only (Zero Data Entry)

**Farmer provides:** Nothing (just installs app or receives first SMS)  
**Farmer receives immediately:**
- Local weather forecasts (block-level)
- Market prices for common crops in their district
- Seasonal agricultural advisories
- Educational content (videos, articles in local language)
- Disease alerts for their region

**Time to value:** < 2 minutes after install  
**Engagement mechanism:** Content feed, push notifications for weather/prices

**Design implication:** The app must have a "guest mode" or "explore mode" that delivers value without registration.

---

### Level 1: Basic Registration (Mobile number + village)

**Farmer provides:** Mobile number, village, primary crop (3 fields)  
**Farmer receives additionally:**
- Crop-specific advisories for their village
- Localized weather alerts (village-level)
- Seasonal reminders relevant to their crop
- SMS advisories (feature-phone farmers)
- Access to agronomist helpline (disease photo upload)

**Time to value:** Immediate after 60-second registration  
**Engagement mechanism:** Personalized notifications, crop-specific content

**Design implication:** Registration must be completable in <60 seconds with just 3 fields. Everything else is optional and collected progressively.

---

### Level 2: Parcel Registration (Add land details)

**Farmer provides:** Approximate land area, irrigation type (2 additional fields)  
**GPS polygon mapping is OPTIONAL at this level.**  
**Farmer receives additionally:**
- Input quantity recommendations calibrated to their land size
- Irrigation scheduling suggestions
- Localized yield benchmarks ("farmers like you in your village average X kg/hectare")
- Insurance eligibility indication

**Time to value:** Within 24 hours (first personalized recommendation)  
**Engagement mechanism:** "Your farm" dashboard showing personalized insights

**Design implication:** Parcel can be created with just area + irrigation type. GPS polygon is a Level 3 enhancement, not a prerequisite.

---

### Level 3: Crop Tracking (Active lifecycle participation)

**Farmer provides:** Crop stage updates (one-tap: "I completed sowing")  
**Farmer receives additionally:**
- Stage-specific reminders ("Time to apply first fertilizer dose")
- Proactive disease alerts based on crop stage + regional patterns
- Expected timeline to harvest
- Comparison with nearby farmers' progress
- Priority access to agronomist advisory

**Time to value:** First reminder within days of crop registration  
**Engagement mechanism:** Timeline view, progress indicators, "what's next" guidance

**Design implication:** Stage updates must be ONE TAP (not multi-step forms). Details are optional.

---

### Level 4: Economics Tracking (Cost and revenue logging)

**Farmer provides:** Approximate costs per category, yield, sale price  
**Farmer receives additionally:**
- Profitability analysis ("You earned ₹X per hectare this season")
- Cost optimization suggestions ("Farmers with similar yield spend 20% less on fertilizer")
- Season-over-season comparison
- Credit/loan eligibility signals
- Insurance claim support data

**Time to value:** End of first crop cycle (profitability report)  
**Engagement mechanism:** "Season report card," peer comparison, financial insights

**Design implication:** Cost entry supports APPROXIMATE values ("about ₹15,000 on fertilizer"). Precision is optional.

---

### Level 5: Long-Term Participation (Multi-season engagement)

**Farmer provides:** Continued participation across seasons  
**Farmer receives additionally:**
- Multi-season trend analysis ("Your yield improved 15% over 3 seasons")
- Personalized crop recommendations based on history
- Premium advisory access
- Credit score building (verifiable farming history)
- Insurance premium optimization
- Government scheme eligibility matching

**Time to value:** After 2+ seasons  
**Engagement mechanism:** "Farming history" portfolio, achievement milestones

---

## Value Exchange Rules

```yaml
value_exchange_rules:

  - never_ask_for_data_without_explaining_farmer_benefit
  - deliver_value_before_requesting_data
  - every_form_field_must_justify_its_existence_to_the_farmer
  - optional_fields_must_be_clearly_optional
  - approximate_data_is_acceptable_at_all_levels
  - farmer_can_participate_at_any_level_without_pressure_to_advance
  - value_increases_with_participation_but_base_value_is_free
```

---

## Feature-Phone Farmer Value Path

Feature-phone farmers cannot use the app. Their value ladder:

| Level | Interaction | Value Received |
|-------|------------|----------------|
| 0 | Enrolled by dealer | Receives SMS weather alerts |
| 1 | Receives crop reminders | Timely stage-specific guidance via SMS |
| 2 | Replies to SMS (YES/HELP) | Confirms actions, requests dealer callback |
| 3 | Dealer logs on behalf | Gets profitability report via dealer |

**Design implication:** Feature-phone farmers receive value through SMS + dealer relay. They are never required to use the app.

---

## Dealer Value Path (Why Dealers Participate)

| Dealer Benefit | Mechanism |
|---------------|-----------|
| Farmer relationship visibility | "My Farmers" dashboard with engagement status |
| Sales intelligence | Know which farmers need which inputs, when |
| Performance recognition | Leaderboard, achievement badges, enterprise visibility |
| Commission tracking | Transparent view of incentive earnings |
| Preferential stock allocation | High-performing dealers get priority supply |
| Enterprise program access | Participation in company campaigns and schemes |
| Reduced farmer churn | Better-served farmers stay loyal to dealer |

---

## MVP Scope Alignment

For MVP, implement Levels 0-3 fully. Level 4 (economics) in simplified form. Level 5 deferred.

| Level | MVP Status | Minimum Implementation |
|-------|-----------|----------------------|
| 0 | ✅ Full | Weather, prices, content feed |
| 1 | ✅ Full | 60-second registration, crop-specific SMS |
| 2 | ✅ Simplified | Area + irrigation (no mandatory GPS polygon) |
| 3 | ✅ Full | One-tap stage updates, reminders |
| 4 | ⚠️ Simplified | Approximate cost entry, basic profitability |
| 5 | ❌ Deferred | Multi-season analytics, credit signals |

---

*End of Farmer Value Ladder*
