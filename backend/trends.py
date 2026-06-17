import re
import logging
from db import get_db_connection

logger = logging.getLogger(__name__)

# Stop words to filter out when tokenizing statements for trending keywords
STOP_WORDS = {
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
    'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
    'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves',
    'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
    'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does',
    'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until',
    'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into',
    'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down',
    'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here',
    'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
    'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now', 'd',
    'll', 'm', 'o', 're', 've', 'y', 'ain', 'aren', 'couldn', 'didn', 'doesn', 'hadn',
    'hasn', 'haven', 'isn', 'ma', 'mightn', 'mustn', 'needn', 'shan', 'shouldn', 'wasn',
    'weren', 'won', 'wouldn', 'claims', 'claim', 'statement', 'says', 'about', 'is', 'the',
    'are', 'would', 'could', 'should', 'people', 'world', 'news', 'new', 'years', 'time'
}

def extract_keywords(text: str) -> list[str]:
    """
    Extracts descriptive keywords from a claim statement.
    Splits by whitespace, strips punctuation, and removes common stop words.
    """
    if not text:
        return []
    
    # Strip non-alphanumeric characters, keep spacing, lowercase it
    cleaned_text = re.sub(r'[^\w\s]', '', text.lower())
    tokens = cleaned_text.split()
    
    keywords = []
    for token in tokens:
        # Keep words longer than 2 characters, exclude numbers and stop words
        if len(token) > 2 and not token.isdigit() and token not in STOP_WORDS:
            keywords.append(token)
            
    return keywords

def log_claim_keywords(text: str):
    """
    Tokenizes the claim text and logs each keyword into the database.
    """
    keywords = extract_keywords(text)
    if not keywords:
        return
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert each keyword with the default CURRENT_TIMESTAMP
        for keyword in keywords:
            cursor.execute(
                "INSERT INTO search_trends (keyword) VALUES (?)",
                (keyword,)
            )
            
        conn.commit()
        conn.close()
        logger.info(f"Logged {len(keywords)} keywords to search_trends: {keywords}")
    except Exception as e:
        logger.error(f"Failed to log keywords to database: {e}")

def get_trending_keywords(limit: int = 6) -> list[str]:
    """
    Retrieves the top N trending keywords in the last 24 hours.
    If database is empty/recent list is small, falls back to a few pre-seeded demo topics.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query top keywords logged in the past 24 hours
        cursor.execute("""
            SELECT keyword, COUNT(*) as count 
            FROM search_trends 
            WHERE created_at >= datetime('now', '-24 hours') 
            GROUP BY keyword 
            ORDER BY count DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        trends = [row['keyword'].capitalize() for row in rows]
        
        # Fallback pre-seeded trending items if database has insufficient queries
        if len(trends) < 3:
            default_trends = ["Carrot Cure", "Eiffel Tower", "Workweek", "COVID Vaccine", "Climate Change", "AI Tech"]
            # Fill with unique default trends
            for item in default_trends:
                if item not in trends and len(trends) < limit:
                    trends.append(item)
                    
        return trends
    except Exception as e:
        logger.error(f"Failed to fetch trending keywords: {e}")
        return ["Carrot Cure", "Eiffel Tower", "Workweek", "COVID Vaccine", "Climate Change", "AI Tech"]
