# RamIA v1 Product Spec

## What RamIA is
RamIA is a simple, local-first crypto wallet and AI-bot rental experience designed for everyday users. It helps people create a wallet, keep control of their backup, get starter coins, send payments with safety guidance, and optionally rent AI bots through a straightforward flow.

## Who it’s for
- People who want a wallet they can run and control from their own machine.
- Users curious about using coins for practical actions instead of speculation.
- Beginners who need clear safety prompts before sending money.
- Users who may want to rent AI bots without learning technical infrastructure.

## What it does
- Guides users through wallet setup and backup in plain language.
- Lets users receive and send RamIA coins.
- Adds an AI Guardian warning step before risky sends.
- Supports an optional Stripe-based bot rental add-on for users who want paid automation.
- Gives a dashboard-style experience that keeps key actions in one place.

## What it does not do
- It is not a full exchange or trading platform.
- It is not a high-frequency or advanced DeFi terminal.
- It is not a custodial bank that stores user seed phrases.
- It does not promise guaranteed profit from coins, mining, or bot rentals.
- It does not replace user responsibility for securing backups and devices.

## Local-first architecture (Netlify site vs local node)
RamIA v1 has two parts with clear roles:

- **Netlify site (front door):**
  - Hosts the public website and onboarding pages.
  - Explains the product, flow, and user actions.
  - Can route users to download/start instructions.

- **Local node (user control layer):**
  - Runs on the user’s machine for wallet operations.
  - Handles keys, signing, and sensitive transaction actions locally.
  - Performs coin state updates and guardian checks as part of local flow.

In short: the Netlify site helps users start, while the local node performs trust-sensitive actions under user control.

## Success criteria for v1
RamIA v1 is successful when:

1. A new user can install and reach the dashboard without developer help.
2. Most users complete wallet creation and confirm backup in one session.
3. Users can acquire test/starter coins and complete a first send.
4. The AI Guardian warning appears at the right time and reduces risky sends.
5. Optional Stripe bot rental can be started by users who want it.
6. Users report that the experience feels clear, safe, and understandable.
