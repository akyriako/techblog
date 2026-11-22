
import type { APIRoute } from 'astro'

const robotsTxt = `
# The Backyard Rack
# Search engines welcome. AI training crawlers can bugger off.

# OpenAI - training
User-agent: GPTBot
Disallow: /

# Anthropic - training
User-agent: ClaudeBot
Disallow: /

# Common Crawl
User-agent: CCBot
Disallow: /

# Google AI training and grounding controls
User-agent: Google-Extended
Disallow: /

# Other AI data collection crawlers
User-agent: Bytespider
User-agent: Meta-ExternalAgent
User-agent: cohere-ai
Disallow: /

# Allow conventional search and AI-assisted discovery
User-agent: *
Allow: /

Sitemap: ${new URL('sitemap-index.xml', import.meta.env.SITE).href}
`.trim()

export const GET: APIRoute = () =>
  new Response(robotsTxt, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  })
