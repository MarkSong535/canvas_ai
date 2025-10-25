import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv(verbose=True)

from markitdown._base_converter import DocumentConverterResult
from crawl4ai import AsyncWebCrawler
from firecrawl import FirecrawlApp

async def firecrawl_fetch_url(url: str):
    from src.logger import logger
    
    try:
        api_key = os.getenv("FIRECRAWL_API_KEY", None)
        if not api_key:
            logger.error("🚨 FIRECRAWL_API_KEY not found in environment variables")
            return None
            
        logger.info(f"🔑 Using Firecrawl API key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")
        
        app = FirecrawlApp(api_key=api_key)
        logger.info(f"🔥 Firecrawl scraping URL: {url}")

        response = app.scrape(url)
        
        logger.info(f"📊 Firecrawl response type: {type(response)}")
        logger.info(f"📊 Firecrawl response attributes: {dir(response)}")
        
        # 检查不同可能的响应格式
        if hasattr(response, 'markdown') and response.markdown:
            logger.info(f"✅ Found markdown content: {len(response.markdown)} chars")
            return response.markdown
        elif hasattr(response, 'data') and hasattr(response.data, 'markdown') and response.data.markdown:
            logger.info(f"✅ Found data.markdown content: {len(response.data.markdown)} chars")
            return response.data.markdown
        elif hasattr(response, 'content') and response.content:
            logger.info(f"✅ Found content: {len(response.content)} chars")
            return response.content
        elif hasattr(response, 'data') and hasattr(response.data, 'content') and response.data.content:
            logger.info(f"✅ Found data.content: {len(response.data.content)} chars")
            return response.data.content
        else:
            logger.warning(f"⚠️ No content found in Firecrawl response")
            if hasattr(response, 'success'):
                logger.info(f"📊 Response success: {response.success}")
            return None

    except Exception as e:
        logger.error(f"❌ Firecrawl fetch failed: {type(e).__name__}: {e}")
        return None

async def fetch_crawl4ai_url(url: str):
    """Fetch content from a given URL using the crawl4ai library."""
    from src.logger import logger
    
    try:
        logger.info(f"🕷️ Crawl4AI processing URL: {url}")
        
        async with AsyncWebCrawler(
            # 配置选项
            headless=True,
            browser_type="chromium",
            verbose=False,
        ) as crawler:
            response = await crawler.arun(
                url=url,
                # 等待页面加载
                wait_for="body",
                # 提取策略
                extraction_strategy="NoExtractionStrategy",
                # 超时设置
                page_timeout=30000,  # 30秒
                # 移除不必要的元素
                remove_overlay_elements=True,
            )

            if response and response.success:
                logger.info(f"✅ Crawl4AI successful: {len(response.markdown)} chars")
                return response.markdown
            else:
                logger.warning(f"⚠️ Crawl4AI failed: success={getattr(response, 'success', False)}")
                if hasattr(response, 'error_message'):
                    logger.warning(f"   Error: {response.error_message}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Crawl4AI exception: {type(e).__name__}: {e}")
        return None

async def fetch_url(url: str) -> Optional[DocumentConverterResult]:
    # Fetch content from a URL using Firecrawl and Crawl4AI.
    from src.logger import logger
    
    logger.info(f"🌐 Starting content fetch for: {url}")

    try:
        logger.info("🔥 [PRIMARY] Attempting content fetch with Firecrawl...")
        firecrawl_result = await firecrawl_fetch_url(url)
        
        if firecrawl_result:
            logger.info("✅ [PRIMARY] Firecrawl content fetch successful")
            return DocumentConverterResult(
                markdown=firecrawl_result,
                title=f"Fetched content from {url}",
            )
        else:
            logger.warning("⚠️ [PRIMARY] Firecrawl returned no content")

        logger.warning("🔄 PRIMARY content fetcher failed, initiating fallback...")
        logger.info("🕷️ [FALLBACK] Attempting content fetch with Crawl4AI...")
        crawl4ai_result = await fetch_crawl4ai_url(url)

        if crawl4ai_result:
            logger.info("✅ [FALLBACK] Crawl4AI content fetch successful")
            return DocumentConverterResult(
                markdown=crawl4ai_result,
                title=f"Fetched content from {url}",
            )
        else:
            logger.warning("⚠️ [FALLBACK] Crawl4AI returned no content")

        logger.error("💥 ALL CONTENT FETCHERS FAILED! No content available")
        return None

    except Exception as e:
        logger.error(f"❌ Content fetch failed with exception: {type(e).__name__}: {e}")
        return None

if __name__ == '__main__':
    import asyncio
    url = "https://www.google.com/"
    result = asyncio.run(firecrawl_fetch_url(url))
    print(result)