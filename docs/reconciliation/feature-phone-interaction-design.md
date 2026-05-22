# Feature-Phone Interaction Design
# Agricultural Operations Intelligence Platform

**Status:** DECIDED  
**Date:** May 21, 2026  
**Purpose:** Define how feature-phone farmers (no smartphone, SMS-only) interact with the platform beyond passive notification receipt.

---

## 1. Context & Problem

Feature-phone farmers (estimated 30-50% of target audience in rural India) currently have:
- ✅ Receive SMS notifications (one-way)
- ❌ No way to acknowledge receipt
- ❌ No way to confirm actions taken
- ❌ No way to report problems
- ❌ No way to request help
- ❌ No feedback loop whatsoever

This makes them purely passive data subjects with zero agency. This design gives them interaction capability within SMS/voice constraints.

---

## 2. Design Principles

```yaml
feature_phone_principles:
  - interaction_must_be_possible_via_SMS_reply
  - no_internet_required
  - no_app_download_required
  - literacy_requirements_minimized (numbers and simple keywords)
  - local_language_support_mandatory
  - dealer_escalation_always_available
  - consent_must_be_obtainable_via_SMS
  - opt_out_must_be_simple
```

---

## 3. SMS Interaction Model

### 3.1 Reply Keywords

All SMS messages from the platform include a reply instruction. Farmers reply with simple keywords or numbers.

```yaml
universal_keywords:
  "1" or "YES" or "HA":
    meaning: confirm / acknowledge / agree
    example: "Reply 1 to confirm you applied fertilizer"

  "2" or "NO" or "NAHI":
    meaning: deny / not done / disagree
    example: "Reply 2 if you have NOT applied fertilizer yet"

  "0" or "HELP" or "MADAD":
    meaning: request dealer callback
    example: "Reply 0 for dealer to call you"

  "STOP" or "BAND":
    meaning: opt out of notifications
    action: deactivate notifications, preserve data, notify dealer

  "HAAL" or "STATUS":
    meaning: request current crop status summary
    action: send SMS with current stage + next action
```

### 3.2 Numbered Menu Responses

For multi-option interactions:

```
SMS from platform:
"Your onion crop - what stage?
1 = Sowing done
2 = Transplanting done  
3 = Flowering started
4 = Harvested
Reply with number"

Farmer replies: "2"
System: Updates stage to TRANSPLANTING_COMPLETED
System: Sends confirmation "Transplanting recorded ✓ Next: fertilizer in 7 days"
```

### 3.3 SMS Confirmation Loop

Every farmer action via SMS follows:

```
Platform sends: Action request / information
Farmer replies: Keyword or number
Platform sends: Confirmation + next expected action
```

No action is taken without confirmation SMS back to farmer.

---

## 4. Interaction Flows

### 4.1 Stage Update via SMS

```yaml
stage_update_sms_flow:

  trigger: Rules Engine determines stage reminder is due
  
  step_1_outbound:
    message: "Namaste [farmer_name]. Your [crop] on [parcel] - has [stage_name] been completed? Reply 1=Yes, 2=No, 0=Help"
    language: farmer_preference
    
  step_2_farmer_reply:
    "1": 
      action: update stage_instance to COMPLETED
      response: "[Stage] recorded ✓ Next: [next_stage_name] expected in [X] days"
    "2":
      action: no state change, schedule follow-up in 7 days
      response: "OK. We will check again in 7 days. Reply 0 if you need help."
    "0":
      action: create dealer_callback_task
      response: "Your dealer [dealer_name] will call you within 24 hours."
    no_reply_in_48h:
      action: notify dealer for follow-up
```

### 4.2 Disease Reporting via SMS

```yaml
disease_report_sms_flow:

  trigger: farmer sends keyword "BIMARI" or "DISEASE" or "ROG" to platform number
  
  step_1_acknowledgment:
    message: "Disease report started. Which crop is affected? Reply with crop name or number from your crops: 1=[crop1], 2=[crop2]"
    
  step_2_farmer_reply:
    reply: "1" (or crop name)
    
  step_3_severity:
    message: "How bad? 1=Small spot, 2=Spreading, 3=Very bad"
    
  step_4_farmer_reply:
    reply: "3"
    
  step_5_confirmation:
    message: "Disease report created for [crop] (severity: HIGH). Expert will review. Your dealer [name] has been notified. They may visit to take photos."
    action: 
      - create disease_report (severity=HIGH, source=SMS, photo_pending=true)
      - notify dealer to visit and capture photos
      - assign to agronomist queue

  note: >
    Feature-phone farmers cannot upload photos. The system creates the report
    and triggers a dealer/field-agent visit to capture visual evidence.
```

### 4.3 Advisory Acknowledgment

```yaml
advisory_acknowledgment_flow:

  trigger: advisory_published for this farmer
  
  outbound:
    message: "[crop] advisory: [short_advisory_text, max 140 chars]. Reply 1=Understood, 0=Need help from dealer"
    
  farmer_reply_1:
    action: mark advisory as ACKNOWLEDGED
    response: none (silent acknowledgment)
    
  farmer_reply_0:
    action: create dealer_callback_task with advisory context
    response: "Dealer [name] will explain this advisory. Expect call within 24 hours."
    
  no_reply_72h:
    action: trigger RULE-013 (dealer follow-up)
```

### 4.4 Consent & Enrollment via SMS

```yaml
consent_flow:

  trigger: dealer enrolls farmer, farmer has feature phone
  
  step_1:
    message: "[Enterprise_name] farming program. You have been registered by [dealer_name]. You will receive crop advisories via SMS. Reply 1=OK, STOP=No thanks"
    
  reply_1:
    action: mark consent as GRANTED, activate notifications
    response: "Welcome! You will receive [crop] advisories. Reply STOP anytime to opt out."
    
  reply_STOP:
    action: mark consent as DENIED, deactivate notifications, notify dealer
    response: "OK. You will not receive messages. Your dealer can re-enroll you anytime."
    
  no_reply_7_days:
    action: send one reminder, then mark as CONSENT_PENDING
    note: do NOT send further messages until consent received
```

### 4.5 Weather Alert

```yaml
weather_alert_flow:

  trigger: environmental_event_reported (severity >= HIGH) in farmer's village
  
  outbound:
    message: "⚠️ [Event_type] alert for [village]. [Severity]. Protect your [crop]. Reply 0 for dealer help."
    priority: CRITICAL
    
  no_reply_expected: true (informational, no action required)
  
  reply_0:
    action: create dealer_callback_task (weather_assistance)
```

---

## 5. Missed-Call Interaction Model

For farmers who cannot type SMS replies (very low literacy):

```yaml
missed_call_interactions:

  platform_short_code: [to be assigned]
  
  farmer_gives_missed_call:
    meaning: "I need help" / "Call me back"
    action:
      - identify farmer by caller ID (mobile number)
      - create dealer_callback_task
      - send SMS: "We received your call. [Dealer_name] will call you back within 24 hours."
    
  platform_gives_missed_call_to_farmer:
    meaning: "Please check your SMS" (attention signal)
    use_case: critical advisory or weather alert sent via SMS
    action: ring once, hang up — farmer checks SMS inbox
```

---

## 6. IVR (Interactive Voice Response) — Future Phase

Not in MVP, but architecturally planned:

```yaml
ivr_future_design:

  purpose: voice-based interaction for illiterate farmers
  
  menu_structure:
    "Press 1": hear current crop advisory (text-to-speech)
    "Press 2": confirm stage completion
    "Press 3": report disease (connect to dealer)
    "Press 4": hear weather forecast
    "Press 0": speak to dealer
    
  language: auto-detect from farmer profile, or "Press 1 for Hindi, 2 for Marathi..."
  
  implementation_phase: Phase 2 (post-MVP)
  architectural_implication: 
    - notification_engine must support IVR as a channel
    - advisory content must have text-to-speech compatible format
    - state machine needs IVR-specific states (CALL_INITIATED, MENU_NAVIGATED, COMPLETED)
```

---

## 7. Dealer Relay Model

For interactions that feature-phone farmers cannot perform directly:

```yaml
dealer_relay:

  what_dealers_do_on_behalf:
    - upload disease photos (farmer reports via SMS, dealer visits for photos)
    - complete detailed forms (farmer confirms stage, dealer adds details)
    - view profitability reports (dealer explains to farmer verbally)
    - manage parcel details (farmer provides info verbally, dealer enters)

  dealer_callback_task:
    created_by: farmer SMS reply "0" or missed call or timeout
    contains:
      - farmer_id
      - context (which advisory/alert/stage triggered this)
      - priority (CRITICAL for disease, MEDIUM for routine)
      - deadline (24 hours for routine, 4 hours for critical)
    
    dealer_sees: task in "My Tasks" queue on mobile app
    dealer_completes: marks task done after calling farmer
    
    sla: 
      routine: 24 hours
      critical: 4 hours
    timeout_action: escalate to field_agent or supervisor
```

---

## 8. SMS Technical Specifications

```yaml
sms_specifications:

  character_limit:
    latin: 160 characters per segment
    unicode (Hindi/Devanagari): 70 characters per segment
    
  multi_part_sms:
    supported: true
    max_segments: 3 (210 characters Devanagari)
    numbering: include "1/2", "2/2" prefix
    
  sender_id:
    type: alphanumeric (e.g., "FARMINT" or enterprise brand)
    registered: per TRAI DLT regulations
    
  template_registration:
    required: yes (Indian DLT compliance)
    all_templates_must_be_pre_registered
    variable_substitution: supported within registered templates
    
  delivery_tracking:
    DLR_available: partial (network dependent)
    fallback: if no DLR in 24h, mark as DELIVERY_UNKNOWN
    
  rate_limiting:
    per_farmer: max 3 SMS per day (configurable)
    per_campaign: max 1 SMS per farmer per campaign per day
    critical_alerts: exempt from rate limiting
    
  opt_out:
    mechanism: reply STOP
    compliance: immediate cessation (TRAI requirement)
    data_retention: farmer data preserved, notifications deactivated
```

---

## 9. Notification State Machine Extension for SMS

```yaml
sms_notification_states:

  additional_states:
    - DELIVERY_UNKNOWN (no DLR received)
    - AWAITING_REPLY (sent, waiting for farmer response)
    - REPLY_RECEIVED (farmer responded)
    - DEALER_ESCALATED (no reply, dealer notified)

  transitions:
    DELIVERED:
      - to: AWAITING_REPLY (if reply expected)
      - to: CLOSED (if informational only)
    
    DELIVERY_UNKNOWN:
      - to: DEALER_ESCALATED (after 24h, for critical messages)
      - to: CLOSED (after 72h, for non-critical)
    
    AWAITING_REPLY:
      - to: REPLY_RECEIVED (farmer replies)
      - to: DEALER_ESCALATED (timeout, per rule configuration)
    
    REPLY_RECEIVED:
      - to: CLOSED (action processed)
```

---

## 10. MVP Scope for Feature-Phone

For the first vertical slice, implement:

```yaml
mvp_feature_phone:
  implemented:
    - consent_flow (enrollment confirmation)
    - stage_update_via_sms (one-tap number reply)
    - advisory_acknowledgment (reply 1 or 0)
    - weather_alerts (informational, no reply needed)
    - opt_out (STOP keyword)
    - dealer_callback_request (reply 0)
    
  deferred:
    - disease_reporting_via_sms (complex multi-step)
    - missed_call_interactions
    - IVR
    - multi-part_SMS_conversations
    - status_request (HAAL keyword)
```

---

## 11. Metrics & Success Criteria

```yaml
feature_phone_metrics:
  - sms_delivery_rate (target: >90%)
  - reply_rate (target: >30% for action-required messages)
  - dealer_callback_completion_rate (target: >80% within SLA)
  - opt_out_rate (monitor: <5% monthly)
  - consent_grant_rate (target: >85%)
  - stage_update_via_sms_rate (target: >40% of feature-phone farmers respond)
```

---

*End of Feature-Phone Interaction Design*
