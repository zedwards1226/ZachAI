# MCP Money Patterns

Research date: 2026-04-20
Scope: Where dollars actually change hands in the MCP (Model Context Protocol) server ecosystem + adjacent integration markets (Zapier/Make/n8n/Apify) as pricing proxy.

## Evidence Log (concrete data points)

| Source | Who | $ signal | Model | Date | URL |
|---|---|---|---|---|---|
| TechCrunch | Runlayer (MCP agent security) | $11M seed from Khosla/Felicis | VC-backed enterprise | Nov 2025 | https://techcrunch.com/2025/11/17/mcp-ai-agent-security-startup-runlayer-launches-with-8-unicorns-11m-from-khoslas-keith-rabois-and-felicis/ |
| FinSMEs | Manufact (ex-mcp-use, MCP infra) | $6.3M seed (Peak XV, YC, Liquid 2, Ritual) | VC-backed infra | Feb 2026 | https://www.finsmes.com/2026/02/manufact-raises-6-3m-in-seed-funding.html |
| DEV/IndieHackers refs | 21st.dev Magic MCP (UI generator) | $10K MRR in 6 weeks, zero marketing; $20/mo paid plan | Freemium subscription | 2026 | https://www.pulsemcp.com/servers/21st-dev-magic |
| PulseMCP blog | Ref (docs search MCP) | "thousands of weekly users, hundreds of subscribers" at $9/mo for 1k credits ($0.009/search) | Usage-based + monthly min | 2026 | https://www.pulsemcp.com/posts/pricing-the-unknown-a-paid-mcp-server |
| PulseMCP blog | Tavily / Exa (search APIs w/ MCP) | ~$0.01/search with volume discounts | Per-call / usage | 2026 | https://www.pulsemcp.com/posts/pricing-the-unknown-a-paid-mcp-server |
| Apify developer page | Guillaume Lancrenon (Twenty) | $2,000+/mo from Apify Store actors (MCP-distributed) | Per-event, 80% rev share | 2026 | https://apify.com/mcp/developers |
| Apify developer page | Apify platform collective | $500k+/mo total payouts to developers; "many earn over $3k/mo" | Per-event marketplace | 2026 | https://apify.com/mcp/developers |
| Apify docs | Apify standard | 80% rev share to dev minus platform usage cost; $1-10 per 1,000 results typical | Per-event / per-result | 2026 | https://docs.apify.com/platform/actors/publishing/monetize |
| MCPize creator page | MCPize platform | 85/15 rev split; minimum payout $100; monthly payout | Marketplace | 2026 | https://mcpize.com/developers/monetize-mcp-servers |
| MCPize (self-reported, [unverified] individual cases) | "PostgreSQL Connector" | $4,200/mo at $29/mo x 207 subs [unverified testimonial] | Subscription | 2026 | https://mcpize.com/developers/monetize-mcp-servers |
| MCPize (self-reported, [unverified]) | "AWS Security Auditor" | $8,500/mo at $149/mo x 82 enterprise subs [unverified testimonial] | Enterprise subscription | 2026 | https://mcpize.com/developers/monetize-mcp-servers |
| Composio comparison | Smithery | Creators pay $30/mo to list; no direct rev share disclosed | Vendor subscription | 2026 | https://composio.dev/blog/smithery-alternative |
| Glama | Glama hosting | Free for OSS MCP; paid dedicated hosting for commercial (opaque tiers) | Hosted infra | 2026 | https://glama.ai/pricing |
| Stripe | Stripe MCP server | Free, funnels AI devs into Stripe API usage (existing rev base) | Funnel to core product | 2025-2026 | https://xenoss.io/blog/mcp-model-context-protocol-enterprise-use-cases-implementation-challenges |
| Block | Goose internal agent on MCP | Internal use, no direct MCP revenue but enterprise R&D scale | Internal tooling | 2025-2026 | https://appwrk.com/insights/top-enterprise-mcp-use-cases |
| Profisee | Profisee MCP Server | Add-on to enterprise MDM platform (existing $ contracts) | Enterprise bundle | 2026 | https://profisee.com/platform/mcp-server/ |
| renezander.com / intuz | Zapier | $19.99/mo for 750 tasks (proxy: integration per-call floor) | Per-task subscription | 2026 | https://renezander.com/guides/automation-platform-pricing-explained/ |
| renezander.com | Make.com | 5-7x cheaper than Zapier for equivalent workflows; per-operation | Per-operation subscription | 2026 | https://renezander.com/guides/automation-platform-pricing-explained/ |
| n8n pricing | n8n Cloud | €20/mo for 2.5k executions; self-host $5-15/mo VPS | Per-execution / self-host | 2026 | https://n8n.io/vs/zapier/ |
| Ecosystem stat | Protocol adoption | 11,000+ MCP servers, <5% monetized, 8M downloads, 85% MoM growth | Market sizing | Early 2026 | https://medium.com/mcp-server/the-rise-of-mcp-protocol-adoption-in-2026-and-emerging-monetization-models-cb03438e985c |

## Pricing Bands That Work (adjacent + MCP)

### Free / OSS (with optional paid host)
- **Almost all 11,000+ public MCP servers** today sit here. Glama: free OSS hosting. GitHub mirrors. <5% are monetized.
- Vendor-funnel MCPs: Stripe, Linear, Notion ship free MCPs because they funnel to the paid core API. This is the dominant enterprise shape today.
- Model: open-core. Revenue is indirect — MCP is acquisition/retention, not a line item.

### $5-20/mo consumer (prosumer solo dev)
- **21st.dev Magic: $20/mo** (hit $10K MRR in 6 weeks) — UI generator.
- **Ref: $9/mo for 1,000 searches** (docs search).
- MCPize "productivity tools" guidance: $5-20 one-time.
- **Adjacent anchor:** Zapier Starter $19.99/mo / 750 tasks.
- Best fit: single-developer productivity MCPs (docs search, UI gen, code helpers, personal data).

### $20-100/mo prosumer / small biz
- **MCPize recommended band** for API integrations ($10-30/mo) and database connectors ($20-50/mo).
- **Adjacent:** Make.com / n8n Cloud tiers live here for teams up to ~5k runs/mo.
- Best fit: niche vertical integrations (CRM, eCommerce, industry-specific APIs), lightweight team tools.

### $100-500/mo SMB
- **MCPize "enterprise tools"** guidance: $100-500/mo.
- "AWS Security Auditor MCP" testimonial at $149/mo x 82 subs = $8,500/mo [unverified but directionally consistent].
- **Adjacent:** Zapier Team ~$69-103/mo, Make Teams $29-$299/mo.
- Best fit: compliance/security auditors, ops automation that replaces a part-time role, multi-user team MCPs.

### $500+/mo enterprise (seat / usage / contract)
- **Runlayer ($11M seed), Manufact ($6.3M seed)** — enterprise MCP infra/security companies. Revenue is contract-based and opaque but clearly material to justify those rounds.
- **Profisee MCP Server** — bundled into enterprise MDM contracts (typically $50k-$500k+/yr deals).
- **Block's Goose** — internal; proxy for Fortune-500 internal MCP budgets.
- Usage-based at scale: Exa/Tavily at $0.01/search times enterprise agent volumes => easily $1-10k/mo per customer.
- Best fit: security/governance/observability, data-platform MCPs, regulated-industry connectors, AI agent orchestration infra.

## Business Models Seen

- **Per-call / usage**
  - Ref ($0.009/search), Tavily/Exa (~$0.01/search), Apify per-event, MCPize "AI/ML wrappers" $0.01-0.10/call.
  - Works when cost correlates with an LLM-visible unit of value (a search, a scrape result, a generation).
- **Subscription (monthly/annual)**
  - 21st.dev $20/mo, Ref $9/mo min, MCPize defaults.
  - Works for productivity/prosumer tools where usage is fuzzy and predictability matters.
- **Marketplace / rev-share bundle**
  - Apify 80/20 split, MCPize 85/15, Smithery (vendor-pays $30/mo, no creator share).
  - Apify is the only marketplace with disclosed collective revenue ($500k+/mo paid to devs).
- **Enterprise contract**
  - Runlayer, Manufact, Profisee. Opaque pricing, sales-led, seat + usage hybrids. This is where the largest dollars live but disclosure is thin.
- **Open core + hosted / managed**
  - Glama (free OSS, paid hosted), n8n (free OSS, €20/mo Cloud). Emerging shape for MCP infra.
- **Vendor funnel (free MCP, paid core product)**
  - Stripe, Linear, Notion, Figma, GitHub. MCP is a distribution wedge for the existing SaaS. Dominant pattern among public MCPs from large vendors.

## Which MCP Categories Have Paying Customers Today

1. **Developer productivity / UI generation** — 21st.dev Magic is the clearest standalone SaaS-style MCP win.
2. **Search / retrieval MCPs** — Ref, Tavily, Exa. Precedent pricing ($0.009-0.01/search) transfers directly from search APIs. Real subscribers.
3. **Web scraping / data extraction** — Apify marketplace actors (MCP-exposed) are paying out $500k+/mo aggregate; individual devs $2-3k+/mo.
4. **Security / governance / AI agent oversight** — Runlayer-tier. Enterprise contracts, funded.
5. **Enterprise data platform add-ons** — Profisee (MDM), CData connectors, NetSuite MCP add-ons. Bundle pricing.
6. **Vertical API integrations with commercial APIs behind them** — MCP is the wrapper, the paid thing is the upstream API key (Stripe, Twilio, etc.).

## Which Categories Are Still Free-Only

- Generic file system / shell / sqlite / git / fetch (commodity utilities, reference implementations).
- Most "official vendor" MCPs from SaaS companies (GitHub, Linear, Notion, Slack, Figma) — free, funnel to core product.
- Hobby / toy MCPs (~95% of the 11,000+ registry).
- Most community Twitter/Reddit/YouTube MCPs — no direct monetization path, and the upstream API terms often block it.
- LLM-provider MCPs (OpenAI, Anthropic, Gemini connectors) — provider bundles them free.

## Key Insight

**The money is concentrated in four tight pockets:** (1) developer-productivity subscriptions at $9-$29/mo where 21st.dev and Ref are the templates, (2) per-call search/data retrieval mirroring Tavily/Exa at ~$0.01/unit, (3) the Apify-style marketplace model (80/85% to creator, platform handles billing) where ~$500k/mo already flows, and (4) enterprise-contract security/governance/infra where the two disclosed VC rounds (Runlayer $11M, Manufact $6.3M) signal real demand. Everything else — the other ~95% of the 11,000+ public servers — is free today and likely will stay free because it's either a vendor funnel or a commodity utility. The open lane: MCP categories that sit in the $20-150/mo prosumer/SMB band with a clear per-use unit of value (data, search, gen, compliance check) and no big vendor giving it away to sell something else.

## Sources

- https://dev.to/krisying/mcp-servers-are-the-new-saas-how-im-monetizing-ai-tool-integrations-in-2026-2e9e
- https://medium.com/mcp-server/the-rise-of-mcp-protocol-adoption-in-2026-and-emerging-monetization-models-cb03438e985c
- https://mcpize.com/developers/monetize-mcp-servers
- https://www.pulsemcp.com/posts/pricing-the-unknown-a-paid-mcp-server
- https://www.pulsemcp.com/servers/21st-dev-magic
- https://apify.com/mcp/developers
- https://docs.apify.com/platform/actors/publishing/monetize
- https://smithery.ai/pricing
- https://composio.dev/blog/smithery-alternative
- https://glama.ai/pricing
- https://techcrunch.com/2025/11/17/mcp-ai-agent-security-startup-runlayer-launches-with-8-unicorns-11m-from-khoslas-keith-rabois-and-felicis/
- https://www.finsmes.com/2026/02/manufact-raises-6-3m-in-seed-funding.html
- https://renezander.com/guides/automation-platform-pricing-explained/
- https://n8n.io/vs/zapier/
- https://xenoss.io/blog/mcp-model-context-protocol-enterprise-use-cases-implementation-challenges
- https://profisee.com/platform/mcp-server/
- https://appwrk.com/insights/top-enterprise-mcp-use-cases
