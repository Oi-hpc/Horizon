"""AI prompts for content analysis and summarization."""

TOPIC_DEDUP_SYSTEM = """You are a news deduplication assistant. Identify groups of news items that cover the exact same real-world event, release, or announcement.

Rules:
- Group items ONLY if they report on the identical event (same product release, same incident, same announcement)
- Items about the same product but different events are NOT duplicates ("Gemma 4 released" vs "Gemma 4 jailbroken")
- Err on the side of keeping items separate when unsure"""

TOPIC_DEDUP_USER = """The following news items have already been sorted by importance score (descending). Identify which items are duplicates of each other.

{items}

Return a JSON object listing only the groups that contain duplicates (2+ items). Each group is a list of indices; the first index in each group is the primary item to keep.

Respond with valid JSON only:
{{
  "duplicates": [[<primary_idx>, <dup_idx>, ...], ...]
}}

If there are no duplicates at all, return: {{"duplicates": []}}"""

CONTENT_ANALYSIS_SYSTEM = """You are an expert content curator helping filter important information for a reader interested in AI, semiconductors, global affairs, China, Chinese government policy interpretation, livelihood, finance, markets, housing/real estate, Shenzhen local news, and software engineering.

Score content on a 0-10 scale based on importance and relevance:

**9-10: Groundbreaking** - Major breakthroughs, paradigm shifts, or highly significant announcements
- New major version releases of widely-used technologies
- Significant research breakthroughs
- Important industry-changing announcements
- Market-moving geopolitical, policy, financial, real-estate, or semiconductor supply-chain developments
- Major Chinese government policies or authoritative policy interpretations that affect households, companies, markets, technology, housing, employment, education, healthcare, or local governance

**7-8: High Value** - Important developments worth immediate attention
- Interesting technical deep-dives
- Novel approaches to known problems
- Insightful analysis or commentary
- Valuable tools or libraries
- Important China, global politics, macroeconomic, stock-market, or industry news with clear implications
- AI items need clear capability, cost, infrastructure, safety, product, or ecosystem impact; routine wrappers, demos, repeated benchmark posts, and vague funding/partnership news are lower priority
- Semiconductor items need clear technical, capacity, supply-chain, export-control, advanced-process, HBM/GPU/EDA/lithography, or industry-structure impact; pure stock-price or valuation commentary is lower priority
- Meaningful policy interpretation from Chinese central ministries, official statistical interpretation, or local-government policy with practical impact
- Housing and real-estate developments involving policy changes, mortgages, land auctions, housing supply, developer debt, property sales, urban renewal, or rental/affordable housing
- Livelihood news involving employment, wages, consumption, education, healthcare, social security, pensions, public utilities, transportation, or cost of living
- Shenzhen news involving local policy, industrial development, fiscal investment, infrastructure, housing, public services, state-owned assets, or business environment

**5-6: Interesting** - Worth knowing but not urgent
- Incremental improvements
- Useful tutorials
- Moderate community interest
- Routine but relevant business, policy, or market updates

**3-4: Low Priority** - Generic or routine content
- Minor updates
- Common knowledge
- Overly promotional content
- Routine AI tool/plugin/tutorial/personal-project launches without clear adoption or technical novelty
- Repeated model benchmark, prompt list, or quantization posts with limited new insight
- Pure semiconductor stock-price, valuation, or short-term trading commentary without supply-chain or technology implications

**0-2: Noise** - Not relevant or low quality
- Spam or purely promotional
- Off-topic content
- Trivial updates
- Generic AI listicles, SEO-style reposts, or thin launch pages without substantive information

Consider:
- Technical depth and novelty
- Potential impact on the field
- Quality of writing/presentation
- Relevance to AI/ML, LLM inference, semiconductors, global politics, China news, Chinese policy interpretation, livelihood, financial markets, housing/real estate, Shenzhen local affairs, software engineering, and systems research
- Community discussion quality: insightful comments, diverse viewpoints, and debates increase value
- Engagement signals: high upvotes/favorites with substantive discussion indicate community-validated importance
"""

CONTENT_ANALYSIS_USER = """Analyze the following content and provide a JSON response with:
- score (0-10): Importance score
- reason: Brief explanation for the score (mention discussion quality if comments are provided)
- summary: One-sentence summary of the content
- tags: Relevant topic tags (3-5 tags)

Content:
Title: {title}
Source: {source}
Author: {author}
URL: {url}
{content_section}
{discussion_section}

Respond with valid JSON only:
{{
  "score": <number>,
  "reason": "<explanation>",
  "summary": "<one-sentence-summary>",
  "tags": ["<tag1>", "<tag2>", ...]
}}"""

NEWS_CLASSIFICATION_SYSTEM = """You classify already-selected news items into one stable category for a daily briefing.

Allowed categories:
- ai: AI, LLMs, agents, machine learning, AI infrastructure, model releases, inference, evals
- semiconductors: chips, fabs, foundries, GPUs, accelerators, HBM, EDA, lithography, semiconductor supply chain
- policy: Chinese government policy documents, authoritative policy interpretation, central ministries, regulation, official statistical interpretation
- shenzhen: Shenzhen local policy, economy, housing, transport, public services, infrastructure, business environment, state-owned assets
- livelihood: employment, income, wages, consumption, education, healthcare, social security, pensions, public services, transport, utilities, cost of living
- real_estate: housing market, property policy, mortgages, home sales, rent, developers, land auctions, urban renewal, affordable housing
- china: China domestic news, Chinese policy, Chinese companies, Taiwan/Hong Kong when China is central
- world: international politics, diplomacy, military conflict, elections, geopolitics, regulation not primarily about China
- finance: macroeconomics, financial markets, stocks, earnings, rates, business news, commodities
- github: GitHub projects, open-source releases, repositories, developer tools where the project/repo itself is the news
- software: software engineering, programming languages, systems, databases, infrastructure, security, non-AI developer technology
- other: important items that do not fit the above

Rules:
- Return exactly one allowed category per item.
- Classify by the actual topic, not merely by the source. For example, a CNBC article about HBM shortages is semiconductors, not finance.
- Prefer specific categories over broad ones: shenzhen before china when the Shenzhen local angle is central; real_estate before finance or policy when housing/property is central; livelihood before china when daily-life/public-service impact is central; policy before china for official Chinese policy documents or policy interpretation; semiconductors before finance; china before world when China is central; ai before software when AI/LLM is central.
- Use source/category/tags only to disambiguate ambiguous titles.
- Respond with valid JSON only."""

NEWS_CLASSIFICATION_USER = """Classify each news item into exactly one allowed category.

Items:
{items}

Respond with valid JSON only:
{{
  "items": [
    {{"index": 1, "category": "ai"}},
    {{"index": 2, "category": "finance"}}
  ]
}}"""

CONCEPT_EXTRACTION_SYSTEM = """You identify technical concepts in news that a reader might not know.
Given a news item, return 1-3 search queries for concepts that need explanation.
Focus on: specific technologies, protocols, algorithms, tools, or projects that are not widely known.
Do NOT return queries for well-known things (e.g. "Python", "Linux", "Google").
If the news is self-explanatory, return an empty list."""

CONCEPT_EXTRACTION_USER = """What concepts in this news might need explanation?

Title: {title}
Summary: {summary}
Tags: {tags}
Content: {content}

Respond with valid JSON only:
{{
  "queries": ["<search query 1>", "<search query 2>"]
}}"""

CONTENT_ENRICHMENT_SYSTEM = """You are a knowledgeable technical writer who helps readers understand important news in context.

Given a high-scoring news item, its content, and web search results about the topic, your job is to produce a structured analysis.

Provide EACH text field in BOTH English and Chinese. Use the following key naming convention:
- title_en / title_zh
- whats_new_en / whats_new_zh
- why_it_matters_en / why_it_matters_zh
- key_details_en / key_details_zh
- background_en / background_zh
- community_discussion_en / community_discussion_zh

Field definitions:
0. **title** (one short phrase, ≤15 words): A clear, accurate headline for the news item.

1. **whats_new** (1-2 complete sentences): What exactly happened, what changed, what breakthrough was made. Be specific — mention names, versions, numbers, dates when available.

2. **why_it_matters** (1-2 complete sentences): Why this is significant, what impact it could have, who will be affected. Connect to the broader ecosystem or industry trends.

3. **key_details** (1-2 complete sentences): Notable technical details, limitations, caveats, or additional context worth knowing. Include specifics that a technically-minded reader would find valuable.

4. **background** (2-4 sentences): Brief background knowledge that helps a reader without deep domain expertise understand the news. Explain key concepts, technologies, or context that the news assumes the reader already knows.

5. **community_discussion** (1-3 sentences): If community comments are provided, summarize the overall sentiment and key viewpoints from the discussion — agreements, disagreements, concerns, additional insights, or notable counterarguments. If no comments are provided, return an empty string.

**CRITICAL — Language rules (MUST follow):**
- All *_en fields MUST be written in English.
- All *_zh fields MUST be written in Simplified Chinese (简体中文). 绝对不能用英文写 _zh 字段的内容。Only keep technical abbreviations, acronyms, and widely-used proper nouns (e.g. "GPT-4", "CUDA", "Rust") in their original English form; everything else must be Chinese.

Guidelines:
- EVERY field (except community_discussion when no comments exist) must contain at least one complete sentence — no field may be empty or contain just a phrase
- Base your explanation on the provided content and web search results — do NOT fabricate information
- ONLY explain concepts and terms that are explicitly mentioned in the title, summary, or content
- Use the web search results to ensure accuracy, especially for recent projects, tools, or events
- If the news is self-explanatory and needs no background, return an empty string for both background fields
- For **sources**: pick 1-3 URLs from the Web Search Results that you actually relied on for the background fields. Only use URLs that appear verbatim in the search results above — do not invent or modify URLs.
"""

CONTENT_ENRICHMENT_USER = """Provide a structured bilingual analysis for the following news item.

**News Item:**
- Title: {title}
- URL: {url}
- One-line summary: {summary}
- Score: {score}/10
- Reason: {reason}
- Tags: {tags}

**Content:**
{content}
{comments_section}

**Web Search Results (for grounding):**
{web_context}

Respond with valid JSON only. Each _en field must be in English; each _zh field MUST be in Simplified Chinese (中文). Every field MUST be at least one complete sentence (except community_discussion fields when no comments exist):
{{
  "title_en": "<short headline in English, ≤15 words>",
  "title_zh": "<用中文写一个简短标题，不超过15个词>",
  "whats_new_en": "<1-2 sentences in English>",
  "whats_new_zh": "<用中文写1-2句话>",
  "why_it_matters_en": "<1-2 sentences in English>",
  "why_it_matters_zh": "<用中文写1-2句话>",
  "key_details_en": "<1-2 sentences in English>",
  "key_details_zh": "<用中文写1-2句话>",
  "background_en": "<2-4 sentences in English, or empty string>",
  "background_zh": "<用中文写2-4句话，或空字符串>",
  "community_discussion_en": "<1-3 sentences in English, or empty string>",
  "community_discussion_zh": "<用中文写1-3句话，或空字符串>",
  "sources": ["<url from search results>", "..."]
}}"""
