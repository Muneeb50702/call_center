# Nexus Dispatch Agent: Complete Project Documentation

## 1. Project Overview
**Nexus Dispatch** is a state-of-the-art, fully autonomous Voice AI Dispatching system designed specifically for the logistics and freight industry. It acts as an intelligent, conversational frontline dispatcher that can interact with truck drivers, carriers, and brokers over VoIP/phone calls in real-time. 

Unlike traditional IVR (Interactive Voice Response) systems, Nexus utilizes advanced Large Language Models (LLMs) to engage in fluid, human-like conversations. It understands trucking jargon, negotiates rates, provides live GPS updates, handles roadside emergencies, and executes complex state-based workflows with strict guardrails.

### 1.1 Technical Stack
- **Orchestration & WebRTC:** LiveKit Agents (Python SDK)
- **Large Language Model (LLM):** Google Gemini 2.5 Flash (Optimized for KV Prompt Caching)
- **Speech-to-Text (STT):** Deepgram `nova-2-conversationalai` (Custom trucking vocabulary/keyterm boosted)
- **Text-to-Speech (TTS):** Deepgram Aura (`aura-orion-en` for a professional, authoritative dispatcher voice)
- **Voice Activity Detection (VAD):** Silero VAD (Custom thresholds to prevent echo and aggressive interruptions)
- **Backend Infrastructure:** FastAPI (TMS APIs), PostgreSQL, Redis
- **Deployment:** Docker & Docker Compose (Containerized microservices)

---

## 2. Architecture & Working Features

The system relies on a **Finite State Machine (FSM) Multi-Agent Architecture**. To prevent AI hallucination and ensure enterprise-grade safety, the AI is split into 12 specialized "Agents." Each agent has access *only* to the specific tools required for its state. 

### 2.1 The 12 Specialized Agents
1. **GreetingAgent (Intent Router):** The frontline router. Answers the call, collects the caller's MC number or name, detects their intent, and seamlessly routes them to the correct workflow.
2. **QualificationAgent (Load Search):** Searches the TMS for available freight matching the driver's origin, destination, and equipment type (e.g., Reefer, Dry Van, Flatbed).
3. **NegotiationAgent:** Handles rate discussions. Presents base rates (USD per mile) and evaluates driver counter-offers using predefined company margins.
4. **BookingAgent:** Finalizes the freight booking, assigns the load to the driver in the TMS, and issues a Booking ID.
5. **CheckCallAgent ("Where is my truck?"):** Looks up real-time GPS coordinates of in-transit loads and relays them to the caller.
6. **ETAUpdateAgent:** Calculates and communicates delivery ETAs, and optionally emails updates to brokers/shippers.
7. **LoadStatusAgent:** Provides general updates (e.g., "Available", "Booked", "In Transit", "Delivered").
8. **DetentionAgent:** Files detention claims for drivers stuck at a facility beyond the standard 2-hour free time window.
9. **BreakdownAgent:** An emergency protocol agent. Logs roadside breakdowns, assesses driver safety, and immediately transfers the call to a human dispatcher for roadside assistance.
10. **DocumentAgent:** Sends critical paperwork via email, including Rate Confirmations, Proof of Delivery (POD), and Bills of Lading (BOL).
11. **OnboardingAgent:** Registers new carriers by collecting their MC number, equipment type, and contact info.
12. **WrapUpAgent:** Professionally terminates the call and logs a brief summary of the conversation to the database.

### 2.2 System Optimizations
To achieve sub-second latency and minimal token costs, the system employs two advanced optimizations:
- **Data Pre-Fetching (Zero LLM Repetition):** When the Intent Router detects a request (e.g., "Where is my truck?"), it programmatically queries the TMS database *before* switching agents. The newly activated agent instantly receives the GPS coordinates in its starting context, allowing it to speak the answer immediately without wasting a tool-calling turn.
- **Static Prefix Caching (Gemini KV Cache):** All 12 agents share a massive, perfectly identical system prompt prefix (containing all company rules and tone guidelines). Google's API automatically caches this prefix, slashing token costs by 80% and drastically reducing Time-to-First-Token (TTFT) latency during state transitions.

---

## 3. Example of a Complete Flow (Truck Dispatching)

This narrative demonstrates a seamless end-to-end flow where a driver calls in, gets routed, searches for a load, negotiates a rate, and finalizes the booking.

**[State: GreetingAgent]**
* **Driver:** "Hey, this is John with MC 123456. I'm empty in Chicago and looking for a load."
* **Nexus:** "Hey John. I see you're looking for freight out of Chicago. Give me one second while I pull up what we have."
*(Nexus silently executes `route_to_load_booking`. The FSM transitions the call to the QualificationAgent).*

**[State: QualificationAgent]**
* **Nexus:** "Alright, I've got a Dry Van load picking up today going from Chicago, Illinois to Dallas, Texas. Are you interested in hearing the rate for that one?"
* **Driver:** "Yeah, what's it paying?"
*(Nexus calls `transition_to_negotiation` and switches states).*

**[State: NegotiationAgent]**
* **Nexus:** "The base rate for that lane is currently $2.10 per mile."
* **Driver:** "Man, fuel is up right now. Can you do $2.30?"
*(Nexus internally calls `negotiate_rate(lane="IL-TX", offer=2.30)`. The TMS accepts the offer).*
* **Nexus:** "I can make $2.30 per mile work for you. Should we lock that in?"
* **Driver:** "Yes, let's book it."
*(Nexus calls `transition_to_booking`).*

**[State: BookingAgent]**
* **Nexus:** "Great. Before I lock it in, just to confirm: Chicago to Dallas at $2.30 per mile. Can I go ahead and finalize this booking?"
* **Driver:** "Yes, go ahead."
*(Nexus calls `confirm_booking` to register the load assignment in the TMS).*
* **Nexus:** "All set! Your booking is confirmed under ID BK-99382."
*(Nexus calls `transition_to_wrap_up`).*

**[State: WrapUpAgent]**
* **Nexus:** "I'll have the rate confirmation emailed over to you right away. Drive safe out there, John. Talk soon."
* **Driver:** "Thanks, bye."

*(Call Disconnects. The system logs a summary of the successful booking to the database).*
