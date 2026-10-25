# Polar org: separate pdf2epub org now or later?

Checked 2026-10-23 against Polar's docs and the live checkout.

## What a Polar org is

A Polar organization is a dashboard and storefront: products, customers, orders, branding, API keys, and payouts. Creating one does not incorporate a company or create a separate legal entity. If the goal is legal separation from Opencorp, that needs a separate business entity, tax registration, bank account, and Stripe account. A new Polar org alone does not do that.

## Facts from Polar docs

- A user can belong to any number of organizations and switch between them from the org picker. [Team Management](https://polar.sh/docs/features/team-management)
- Each org needs a payout account. Polar uses Stripe Connect Express. A payout account can be linked to only one org. A new org means new Stripe onboarding, identity/business details, bank account, and review. [Payout Accounts](https://polar.sh/docs/features/finance/accounts)
- New orgs created on or after 2026-05-27 start on Starter: 5% + 50 cents per transaction. Orgs created before that date keep the Early Member rate: 4% + 40 cents, plus 0.5% on subscriptions. [Fees](https://polar.sh/docs/merchant-of-record/fees)
- Polar documents migrating from Stripe and migrating away from Polar. It does not document a one-click product or subscriber transfer between Polar orgs. Recreating the product and updating the checkout link is easy. Moving existing subscribers would need support.

## Live checkout

`https://buy.polar.sh/polar_cl_1jZLYsY7lODWs2QOnhNALMww3O7if69LL4nRQ1JiNmJ` now shows the pdf2epub name above `pdf2epub Shelf`.

## Outcome (2026-10-25)

The separate `pdf2epub` org was created anyway, on the reasoning that brand separation was worth the higher Starter rate while there are still no paying customers. Both products and both checkout links now live there, the org passed review, and payments work. Nothing is left in Opencorp.

The tradeoff stands: Starter is 5% + 50 cents per transaction, versus 4% + 40 cents on the older Opencorp org. Revisit only if volume makes that difference worth migrating back.

The original analysis, kept for reference:

Do not create a second org now.

Reasons:
1. There are no confirmed paying customers, so there is nothing to protect or migrate yet.
2. A new org adds Stripe onboarding, a second payout account, a fresh review, and the higher Starter rate, for zero current revenue.
3. If the only problem is checkout branding, first check whether the existing org's name and logo can be changed to pdf2epub. That keeps the existing payout setup and the Early Member rate.
4. If Opencorp must stay as an umbrella brand and you want pdf2epub separate, revisit when a paying customer is imminent or when revenue covers the extra setup. At that point, recreate the product, update `SHELF_URL`, and handle any subscribers manually.

If "no paid things for now" means pausing Shelf, leave Polar alone entirely. Revisit the org split when Shelf is turned back on.
