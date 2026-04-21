# MCP Market Map

**Generated:** 2026-04-20
**Author:** MARKET-SCANNER (supply-side recon)
**Scope:** What MCP servers exist today, how popular they are, which categories are saturated. No demand/pricing analysis — that is handled by parallel agents.

## Context & Ecosystem Size

- **~12,000+ MCP servers** indexed across public registries by March 2026 (per MCP Market, MCP Directory).
- **Glama registry:** 21,854 servers listed as of 2026-04-20.
- **Smithery registry:** ~6,000–7,000 servers (Mar 2026).
- **Official modelcontextprotocol/servers repo:** 84.2k GitHub stars, now trimmed to 7 reference servers (Everything, Fetch, Filesystem, Git, Memory, Sequential Thinking, Time). Thirteen previously-official servers (Brave Search, GitHub, GitLab, Google Drive, Postgres, Slack, etc.) moved to `servers-archived` — the community now owns those spaces.
- **Quality note:** Only ~12.9% of all MCP servers score "high trust" (>=70/100 on documentation/maintenance/reliability). The long tail is abandonware.

Registry access during research:
- GitHub (official repo, punkpeye awesome list, best-of list): OK
- Glama: OK
- Smithery homepage: HTTP 403 (blocked bot) — compensated via derived data (pedrojaques99/popular-mcp-servers pulls Smithery install counts)
- mcpmarket.com leaderboards: HTTP 429 (rate limited)
- mcpize.com / mcpservers.org / apify MCP: not probed (sufficient data from above)

---

## Top ~50 MCP Servers (by popularity / install signal)

Ranking blends: GitHub stars, Glama weekly downloads, Smithery install/use counts, coverage in curated lists (punkpeye, popularaitools 50-best, mcpmanager top-50, fastmcp top-10). Where two signals diverge strongly, both are noted.

| # | Name | Category | Registry | Install signal | URL |
|---|------|----------|----------|----------------|-----|
| 1 | GitHub MCP Server | Git / Code hosting | Official GH + all registries | 28,300+ GH stars (highest in ecosystem); 2,890+ Smithery uses | https://github.com/github/github-mcp-server |
| 2 | Playwright MCP (Microsoft) | Browser automation | Glama + Smithery | 31,102 GH stars; 2.6M weekly downloads; 257+ Smithery uses | https://github.com/microsoft/playwright-mcp |
| 3 | Figma MCP | Design | Official Figma | 12,000+ GH stars | https://www.figma.com/developers/mcp |
| 4 | Filesystem (official) | Filesystem | Official | Bundled in 84.2k-star ref repo; default in most clients | https://github.com/modelcontextprotocol/servers |
| 5 | Sequential Thinking (official) | Reasoning utility | Official | 5,550+ Smithery uses (top server by install) | https://github.com/modelcontextprotocol/servers |
| 6 | wcgw (shell/coding agent) | Command line / code exec | Smithery | 4,920+ Smithery uses | https://github.com/rusiaaman/wcgw |
| 7 | Fetch (official) | HTTP / web content | Official | 269+ Smithery uses; default install | https://github.com/modelcontextprotocol/servers |
| 8 | Memory / Knowledge Graph (official) | Memory | Official | 263+ Smithery uses | https://github.com/modelcontextprotocol/servers |
| 9 | Brave Search | Web search | Community (archived official) | 680+ Smithery uses | https://github.com/modelcontextprotocol/servers-archived |
| 10 | Puppeteer MCP | Browser automation | Community | Widely forked; top-5 in popularaitools list | https://github.com/modelcontextprotocol/servers-archived |
| 11 | Supabase MCP | Database / BaaS | Official Supabase | Top-3 DB server across multiple lists | https://github.com/supabase-community/supabase-mcp |
| 12 | PostgreSQL MCP | Database | Community + archived official | Default DB MCP in most stacks | https://github.com/modelcontextprotocol/servers-archived |
| 13 | SQLite Server | Database | Smithery | 274+ Smithery uses | https://smithery.ai |
| 14 | Slack MCP | Communication | Community (archived official) | Ranked #1 communication slot in 50-best lists | https://github.com/modelcontextprotocol/servers-archived |
| 15 | Discord MCP | Communication | Community | Common top-5 comms server | Multiple forks |
| 16 | Notion MCP | Productivity / docs | Official Notion | Top productivity slot | https://github.com/makenotion/notion-mcp-server |
| 17 | Linear MCP | Project mgmt | Official Linear | Standard PM slot | https://linear.app/changelog/mcp |
| 18 | Jira MCP | Project mgmt | Atlassian + community | Enterprise standard | Multiple |
| 19 | Stripe MCP | Payments / business | Official Stripe | Official — dominant in payments category | https://stripe.com/docs/mcp |
| 20 | Sentry MCP | Error monitoring | Official Sentry | Official dominant | https://sentry.io |
| 21 | Cloudflare MCP | Cloud / infra | Official Cloudflare | Official dominant | https://github.com/cloudflare/mcp-server-cloudflare |
| 22 | AWS Labs MCP | Cloud | Official (awslabs/mcp) | Umbrella of official AWS servers | https://github.com/awslabs/mcp |
| 23 | Terraform MCP (HashiCorp) | Infra-as-code | Official HashiCorp | Official | https://github.com/hashicorp/terraform-mcp-server |
| 24 | Pulumi MCP | Infra-as-code | Official Pulumi | Official | https://github.com/pulumi/mcp-server |
| 25 | Docker MCP | Dev infra | Community / Docker | Standard | Multiple |
| 26 | Firecrawl MCP | Web scraping | Official Firecrawl | Top scraper | https://github.com/mendableai/firecrawl-mcp-server |
| 27 | Browserbase MCP | Browser cloud | Official Browserbase | Cloud browser leader | https://github.com/browserbase/mcp-server-browserbase |
| 28 | Stagehand MCP | Browser automation | Official Browserbase | AI-native browser | https://github.com/browserbase/stagehand |
| 29 | Exa MCP | Web search | Official Exa | 171+ Smithery uses; dominant semantic search | https://github.com/exa-labs/exa-mcp-server |
| 30 | Perplexity MCP | Search | Community / Perplexity | Common search slot | Multiple |
| 31 | Tavily MCP | Search | Official Tavily | AI-first search | https://github.com/tavily-ai/tavily-mcp |
| 32 | Google Drive MCP | Productivity / storage | Archived official | Common | https://github.com/modelcontextprotocol/servers-archived |
| 33 | Gmail MCP | Email | Community | Standard email MCP | Multiple |
| 34 | Obsidian MCP | Notes | Community | 144+ Smithery uses | Multiple |
| 35 | Airtable MCP | Database / productivity | Community | Standard | Multiple |
| 36 | Todoist MCP | Tasks | Community | Standard task mgr | Multiple |
| 37 | MongoDB MCP | Database | Official MongoDB | Official | https://github.com/mongodb-js/mongodb-mcp-server |
| 38 | Redis MCP | Database / cache | Official Redis | Official | https://github.com/redis/mcp-redis |
| 39 | BigQuery MCP | Data warehouse | Community + Google | Analytics top-5 | Multiple |
| 40 | Snowflake MCP | Data warehouse | Community / Snowflake | Analytics top-5 | Multiple |
| 41 | Elasticsearch MCP | Search / analytics | Community / Elastic | Standard | Multiple |
| 42 | Grafana MCP | Observability | Official Grafana | Official | https://github.com/grafana/mcp-grafana |
| 43 | PostHog MCP | Analytics | Official PostHog | Official | https://github.com/posthog/posthog-mcp |
| 44 | Desktop Commander | Local shell / filesystem | Smithery | 199+ Smithery uses | https://github.com/wonderwhy-er/DesktopCommanderMCP |
| 45 | iTerm MCP | Terminal | Smithery | 402+ Smithery uses | Multiple |
| 46 | Hugging Face MCP | AI/ML | Official HF | Model-hub access leader | https://github.com/evalstate/mcp-hfspace |
| 47 | Replicate MCP | AI/ML | Community | Model execution | Multiple |
| 48 | Ollama MCP | AI/ML local | Community | Local LLM ops | Multiple |
| 49 | Anthropic / OpenAI proxy MCPs | AI/ML | Community | Model-chain orchestration | Multiple |
| 50 | MCP Server Chart (AntV) | Data viz | Official AntV | 3,952 GH stars; 8,329 weekly downloads | https://github.com/antvis/mcp-server-chart |
| 51 | Time (official) | Utility | Official | Ships with every default client | https://github.com/modelcontextprotocol/servers |
| 52 | Twilio MCP | SMS / comms | Official-ish | Standard SMS slot | Multiple |

Honorable mentions by install pull: TaskManager (374 Smithery uses), Web Research (533), Dice Roller (246), Docfork (463 GH stars — docs for 9000+ libs).

---

## Category Saturation

Categories taken from Glama's category filter (~50 categories) + punkpeye's awesome-list headings (~50 categories) + popularaitools' 10-bucket taxonomy. Server-count estimates drawn from Glama filter pages + awesome list entries; saturation is a qualitative judgment based on count AND how large a moat the leader has.

| Category | # of servers (est) | Top server | Saturation | No-build? |
|---|---|---|---|---|
| Filesystem / local files | 200+ | Official Filesystem + Desktop Commander | HIGH | YES |
| Browser automation (general) | 500+ | Playwright MCP (Microsoft, 31k stars, 2.6M DL/wk) | HIGH | YES |
| Web search (Google/Brave/Tavily/Exa/Perplexity) | 300+ | Brave Search / Exa / Tavily — multi-leader | HIGH | YES |
| GitHub / Git hosting | 100+ | GitHub MCP (28k stars, official) | HIGH | YES |
| Postgres / SQL databases | 400+ | Postgres MCP + Supabase | HIGH | YES |
| SQLite / local DB | 150+ | SQLite Server (Smithery default) | HIGH | YES |
| Slack / Discord / chat comms | 250+ | Slack MCP + Discord MCP | HIGH | YES |
| Notion / Obsidian / notes | 200+ | Notion official | HIGH | YES |
| Knowledge graph / memory | 150+ | Official Memory server | HIGH | YES |
| Sequential thinking / reasoning utilities | 100+ | Official Sequential Thinking (5.5k Smithery) | HIGH | YES |
| Web scraping (Firecrawl-style) | 400+ | Firecrawl + Browserbase | HIGH | YES |
| Fetch / HTTP client | 150+ | Official Fetch | HIGH | YES |
| AWS / Azure / GCP cloud | 500+ | AWS Labs MCP, Cloudflare MCP | HIGH | YES |
| Terraform / Pulumi / IaC | 80+ | HashiCorp Terraform (official) | HIGH | YES |
| Docker / containers | 100+ | Docker MCP | MEDIUM-HIGH | YES |
| Linear / Jira / PM tools | 150+ | Linear official + Jira | HIGH | YES |
| Figma / design | 80+ | Figma official (12k stars) | HIGH | YES |
| Gmail / email | 120+ | Gmail MCP forks | HIGH | YES |
| Google Drive / Dropbox | 80+ | GDrive (archived official) | MEDIUM-HIGH | YES |
| BigQuery / Snowflake / data warehouse | 100+ | BigQuery, Snowflake | MEDIUM-HIGH | YES |
| Elasticsearch / search backend | 60+ | Elastic MCP | MEDIUM | caution |
| Grafana / Prometheus / observability | 80+ | Grafana (official) | MEDIUM-HIGH | YES |
| Sentry / error tracking | 40+ | Sentry (official) | MEDIUM-HIGH | YES |
| PostHog / Mixpanel / product analytics | 50+ | PostHog (official) | MEDIUM | caution |
| Stripe / payments | 30+ | Stripe official | MEDIUM-HIGH | YES |
| AI/ML model hubs (HF/Replicate/Ollama/OpenAI) | 300+ | HF MCP, Ollama MCP | HIGH | YES |
| Diagram / Mermaid / Excalidraw | 40+ | Excalidraw + Mermaid | MEDIUM | caution |
| Data viz / charts | 50+ | MCP Server Chart (AntV) | MEDIUM | caution |
| Finance data (broad) | ~300 servers on Glama finance filter | Trading212, Helium (both <30 stars) | MEDIUM — fragmented, NO DOMINANT PLAYER | OPPORTUNITY |
| Crypto / blockchain | 200+ | NEAR, Gitopia, Pentagonal — all low install | MEDIUM — fragmented | caution |
| Security / compliance / audit | 832 on Glama | Pentagonal (239 DL, focused only on smart-contract audits) | MEDIUM — most entries shallow | OPPORTUNITY |
| Command line / shell / PTY | 150+ | wcgw, Desktop Commander, iTerm | HIGH | YES |
| Code execution sandboxes | 80+ | yepcode, pydantic-ai mcp-run-python, piston | MEDIUM-HIGH | caution |
| Coding agents / kanban / workflow | 60+ | kagan, forge, ooples console-automation | MEDIUM | caution |
| Aggregators / MCP gateways | 50+ | 1mcp/agent, mcp-gateway | MEDIUM | caution |
| Biology / medicine / bioinformatics | 40+ | opengenes-mcp, fulcra-context | LOW-MEDIUM | OPPORTUNITY |
| Architecture & design (diagrams/CAD) | 30+ | Excalidraw-architect, ai-diagram-maker | LOW-MEDIUM | OPPORTUNITY |
| Art & culture (Spotify/Photopea/Flux) | 40+ | gupta-kush spotify-mcp (93 tools), photopea-mcp | LOW-MEDIUM | caution |
| Calendar / scheduling | 30+ | Google Calendar forks | LOW-MEDIUM | caution |
| CRM (Salesforce/HubSpot/Pipedrive) | 30+ | No clear leader | LOW-MEDIUM | OPPORTUNITY |
| E-commerce / Shopify / eBay / Amazon | 25+ | Shopify Dev MCP (official-ish) | LOW-MEDIUM | caution (Shopify locked down) |
| Accounting / bookkeeping (QuickBooks, Xero) | <15 | None dominant | LOW | OPPORTUNITY |
| Legal / contracts / document review | <10 | None | LOW | OPPORTUNITY |
| Healthcare / EMR / HIPAA | <15 | None | LOW | OPPORTUNITY (regulated) |
| Manufacturing / IoT / factory | ~10 | Tulip MCP (19 stars) | LOW | OPPORTUNITY |
| Real estate / MLS | <10 | None | LOW | OPPORTUNITY |
| Insurance / claims | <5 | None | LOW | OPPORTUNITY |
| Education / LMS / Canvas | ~15 | None dominant | LOW | OPPORTUNITY |
| Travel / booking APIs | ~20 | None dominant | LOW | caution |
| Government / civic data | <15 | None | LOW | OPPORTUNITY |
| Energy / utilities / grid | <10 | None | LOW | OPPORTUNITY |
| Physical / logistics / shipping | <20 | None dominant | LOW-MEDIUM | OPPORTUNITY |

---

## 10 Most Saturated Categories (DO NOT BUILD HERE)

Ordered by combination of server count + leader dominance + how entrenched defaults are:

1. **Browser automation** — Microsoft Playwright MCP (31k stars, 2.6M weekly DL). Any new browser server must beat Playwright + Puppeteer + Browserbase + Stagehand. Don't.
2. **Web search** — Brave + Exa + Tavily + Perplexity + SearXNG + Firecrawl all active. Funded leaders. Don't.
3. **GitHub / Git hosting** — Official GitHub MCP has 28k stars, first-party, 51 tools. Game over.
4. **Postgres / SQL databases** — Multiple officials (Postgres, Supabase, MongoDB, Redis) + 400+ community. Saturated.
5. **Filesystem / local files** — Official Filesystem + Desktop Commander (199 Smithery) ship in every default client. Saturated.
6. **Knowledge graph / memory** — Official Memory server is the community default (263 Smithery uses). Competing is pointless.
7. **Slack / Discord / team chat** — Saturated with both official-community pairs and long tail.
8. **Sequential thinking / reasoning utilities** — Official server is the #1 installed MCP on Smithery (5,550 uses). Capped market.
9. **Cloud platforms (AWS / Cloudflare / Terraform)** — First-party officials from AWS Labs, HashiCorp, Pulumi, Cloudflare dominate. Don't.
10. **Notion / Obsidian / note-taking** — Official Notion + mature Obsidian forks. Saturated.

Runners-up that are close to no-build: Figma (official), Linear/Jira, Firecrawl scraping, HuggingFace/Ollama model hubs, command-line/shell MCPs.

---

## Sparse Areas (potential opportunities — supply-side only, demand unknown)

Areas where server count is low AND/OR no entrant has meaningful install traction (>100 GH stars). I am only flagging supply gaps — whether anyone wants to pay for these is Agent 2/3's job.

- **Accounting / bookkeeping** — QuickBooks, Xero, FreshBooks MCPs essentially absent.
- **Healthcare / EMR / HIPAA-compliant workflows** — Regulated space, very few servers, zero dominant player.
- **Legal tech** — Contract review, e-discovery, docket tracking, CLM (Clio, NetDocs) all empty.
- **Real estate** — MLS feeds, Zillow/Redfin wrappers, property mgmt (AppFolio, Buildium) absent.
- **Insurance** — Claims, policy admin, underwriting — empty.
- **Government / civic data** — Federal Register, SAM.gov, state procurement feeds, courts — sparse.
- **Energy / utilities** — Grid data, demand response, commodity-specific feeds beyond OilPriceAPI — thin.
- **Manufacturing / IoT** — Tulip exists with 19 stars; MES, SCADA, OPC-UA bridges mostly missing.
- **Finance (retail tools)** — 300 servers listed but no leader above ~30 stars; most are narrow API wrappers. Room for a serious aggregator (brokerage + market data + portfolio analytics).
- **CRM** — Salesforce/HubSpot/Pipedrive wrappers exist but none dominant; quality bar is low.
- **Education / LMS** — Canvas, Blackboard, Moodle integrations mostly absent.
- **Calendar / scheduling** — Google Calendar forks only; no polished multi-calendar MCP.
- **Physical logistics** — Shipping carriers (FedEx, UPS, USPS), warehouse mgmt, carrier-relationship — thin.
- **Audit / governance / SOC2 evidence collection** — 832 "security" servers on Glama but mostly trivial wrappers; full accountability-chain gateways are a flagged gap (per DX Heroes, MCP Manager governance reports).
- **Cross-tool orchestration with policy / approvals** — Attest MCP-style "scoped agent credentials + approvals + audit trail" has essentially one entrant.

### Cross-cutting supply gaps called out by the ecosystem itself
- **Quality/production-readiness:** 87% of existing MCPs are below "high trust" threshold. A "verified / SLA-backed" version of any existing category is a supply gap even where raw counts are high.
- **Enterprise auth / SSO / audit trail across servers:** MCP 2026 roadmap flags this; very few gateways do it end-to-end.
- **Billing / metering middleware for paid MCP endpoints:** Emerging (MCP-Hive) but largely empty.

---

## Sources

- https://github.com/modelcontextprotocol/servers (official reference repo, 84.2k stars, 2026-04-20)
- https://github.com/punkpeye/awesome-mcp-servers (85.2k stars, 50+ categories)
- https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md
- https://glama.ai/mcp/servers (21,854 servers, 2026-04-20 snapshot)
- https://glama.ai/mcp/servers?categories=developer-tools | databases | browser-automation | search | finance | blockchain | security
- https://github.com/tolkonepiu/best-of-mcp-servers (ranked list, weekly updates)
- https://github.com/pedrojaques99/popular-mcp-servers (derives Smithery install counts)
- https://popularaitools.ai/blog/50-best-mcp-servers-2026
- https://mcpmanager.ai/blog/most-popular-mcp-servers/
- https://fungies.io/best-mcp-servers-developers-2026/
- https://mcp.directory/blog/most-popular-mcp-tools-2026
- https://fastmcp.me/blog/top-10-most-popular-mcp-servers (redirected to mcp.directory)
- https://medium.com/mcp-server/the-rise-of-mcp-protocol-adoption-in-2026-and-emerging-monetization-models
- https://dxheroes.io/insights/mcp-governance-landscape-early-2026
- https://mcpmanager.ai/blog/mcp-governance/

### Registry access notes
- Smithery.ai homepage returned HTTP 403 during direct WebFetch; install-count data sourced from pedrojaques99 Smithery scrape + mcpmanager's top-50 post.
- mcpmarket.com leaderboards returned HTTP 429; compensated via overlapping coverage from other lists.
- mcpize.com / mcpservers.org / Apify MCP not probed — existing coverage already saturates the top-50 ranking, and marginal signal would not change the saturation ratings.
