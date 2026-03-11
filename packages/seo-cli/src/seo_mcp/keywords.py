import logging
from typing import List, Optional, Any, Dict

import requests


logger = logging.getLogger(__name__)


def _unwrap_variant(value: Any) -> Any:
    """Unwrap Option-style lists returned by Ahrefs (e.g. ["Some", {...}])."""
    visited: set[int] = set()
    while isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
        marker = value[0].lower()
        if marker not in {"some", "ok", "result"}:
            break
        next_value = value[1]
        value_id = id(next_value)
        if value_id in visited:
            break
        visited.add(value_id)
        value = next_value
    return value


def _extract_payload(keyword_data: Any) -> Optional[Dict[str, Any]]:
    """Find the dict that contains the keyword suggestion payload."""
    candidate = _unwrap_variant(keyword_data)
    if isinstance(candidate, dict):
        # Some responses wrap the payload under a "data" key
        data_field = candidate.get("data")
        if isinstance(data_field, dict):
            return data_field
        return candidate
    if isinstance(candidate, list):
        for item in candidate:
            payload = _extract_payload(item)
            if isinstance(payload, dict):
                return payload
    return None


def _ensure_list(section: Any) -> List[Any]:
    """Return a flat list of ideas from a section of the payload."""
    section = _unwrap_variant(section)
    if not section:
        return []
    if isinstance(section, list):
        # If this looks like an Option-style list, unwrap nested dicts
        if len(section) == 2 and isinstance(section[0], str) and isinstance(section[1], list):
            return _ensure_list(section[1])
        return section
    if isinstance(section, dict):
        for key in ("results", "items", "list", "data"):
            value = section.get(key)
            items = _ensure_list(value)
            if items:
                return items
        # Sometimes the section itself is a single idea dict
        return [section]
    return []


def _get_value(source: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    """Fetch first non-empty value for the provided keys."""
    for key in keys:
        if key in source:
            value = _unwrap_variant(source[key])
            if value not in (None, "", [], {}):
                return value
    return None


def _normalise_idea(raw_idea: Any, idea_type: str) -> Optional[Dict[str, Any]]:
    """Convert raw idea payload into a flat dict with consistent fields."""
    idea = _unwrap_variant(raw_idea)
    if isinstance(idea, list):
        # Find the first dict inside the list
        for item in idea:
            normalised = _normalise_idea(item, idea_type)
            if normalised:
                return normalised
        return None
    if not isinstance(idea, dict):
        return None

    metrics = idea.get("metrics")
    if isinstance(metrics, dict):
        metrics = _unwrap_variant(metrics)
    else:
        metrics = {}

    keyword_value = _get_value(
        idea,
        ["keyword", "kw", "phrase", "query", "text", "value"]
    )
    if isinstance(keyword_value, dict):
        keyword_value = _get_value(
            keyword_value,
            ["keyword", "kw", "phrase", "query", "text", "value"]
        )

    difficulty_value = _get_value(
        idea,
        ["difficultyLabel", "difficulty", "difficulty_text"]
    )
    if difficulty_value is None and isinstance(metrics, dict):
        difficulty_value = _get_value(
            metrics,
            ["difficultyLabel", "difficulty", "kd", "keywordDifficulty"]
        )

    volume_value = _get_value(
        idea,
        ["volumeLabel", "volume", "searchVolume"]
    )
    if volume_value is None and isinstance(metrics, dict):
        volume_value = _get_value(
            metrics,
            ["volumeLabel", "volume", "searchVolume"]
        )

    country_value = _get_value(
        idea,
        ["country", "countryCode", "location"]
    )

    if not keyword_value:
        return None

    result: Dict[str, Any] = {
        "keyword": keyword_value,
        "type": idea_type
    }
    if difficulty_value is not None:
        result["difficulty"] = difficulty_value
    if volume_value is not None:
        result["volume"] = volume_value
    if country_value is not None:
        result["country"] = country_value

    return result


def format_keyword_ideas(keyword_data: Any) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Format raw API response into structured keyword idea buckets."""
    payload = _extract_payload(keyword_data)
    if not isinstance(payload, dict):
        logger.debug("Unable to locate keyword ideas payload: %s", type(keyword_data))
        return None

    regular_ideas: List[Dict[str, Any]] = []
    question_ideas: List[Dict[str, Any]] = []

    all_section = payload.get("allIdeas")
    for idea in _ensure_list(all_section):
        formatted = _normalise_idea(idea, "regular")
        if formatted:
            regular_ideas.append(formatted)

    question_section = payload.get("questionIdeas")
    for idea in _ensure_list(question_section):
        formatted = _normalise_idea(idea, "question")
        if formatted:
            question_ideas.append(formatted)

    all_ideas = regular_ideas + question_ideas
    if not all_ideas:
        logger.debug("No keyword ideas found after normalisation")
        return None

    logger.debug(
        "Returning %s keyword ideas (regular=%s, questions=%s)",
        len(all_ideas),
        len(regular_ideas),
        len(question_ideas),
    )
    return {
        "ideas": regular_ideas,
        "questionIdeas": question_ideas,
        "all": all_ideas
    }


def get_keyword_ideas(token: str, keyword: str, country: str = "us", search_engine: str = "Google") -> Optional[Dict[str, Any]]:
    if not token:
        return None
    
    url = "https://ahrefs.com/v4/stGetFreeKeywordIdeas"
    payload = {
        "withQuestionIdeas": True,
        "captcha": token,
        "searchEngine": [search_engine],  # API expects array format
        "country": country,
        "keyword": keyword  # API expects string, not array
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.debug(
                "Keyword ideas API returned status code %s for keyword=%s",
                response.status_code,
                keyword,
            )
            return None
        
        data = response.json()
        
        # DEBUG: Log the actual API response structure
        logger.debug(
            "API response for keyword='%s': type=%s, content=%s",
            keyword,
            type(data),
            str(data)[:500],
        )
        formatted = format_keyword_ideas(data)
        logger.debug("Formatted keyword ideas for '%s': %s", keyword, formatted)
        if not formatted:
            return None

        return {
            "keyword": keyword,
            "country": country,
            "searchEngine": search_engine,
            **formatted
        }
    except Exception as e:
        logger.exception("Exception in get_keyword_ideas for keyword='%s'", keyword)
        return None


def get_keyword_difficulty(token: str, keyword: str, country: str = "us") -> Optional[Dict[str, Any]]:
    """
    Get keyword difficulty information
    
    Args:
        token (str): Verification token
        keyword (str): Keyword to query
        country (str): Country/region code, default is "us"
        
    Returns:
        Optional[Dict[str, Any]]: Dictionary containing keyword difficulty information, returns None if request fails
    """
    if not token:
        return None
    
    url = "https://ahrefs.com/v4/stGetFreeSerpOverviewForKeywordDifficultyChecker"
    
    payload = {
        "captcha": token,
        "country": country,
        "keyword": keyword
    }
    
    headers = {
        "accept": "*/*",
        "content-type": "application/json; charset=utf-8",
        "referer": f"https://ahrefs.com/keyword-difficulty/?country={country}&input={keyword}"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
        
        data: Optional[List[Any]] = response.json()
        # 检查响应数据格式
        if not isinstance(data, list) or len(data) < 2 or data[0] != "Ok":
            return None
        
        # 提取有效数据
        kd_data = data[1]
        
        # 格式化返回结果
        result = {
            "difficulty": kd_data.get("difficulty", 0),  # Keyword difficulty
            "shortage": kd_data.get("shortage", 0),      # Keyword shortage
            "lastUpdate": kd_data.get("lastUpdate", ""), # Last update time
            "serp": {
                "results": []
            }
        }
        
        # 处理SERP结果
        if "serp" in kd_data and "results" in kd_data["serp"]:
            serp_results = []
            for item in kd_data["serp"]["results"]:
                # 只处理有机搜索结果
                if item.get("content") and item["content"][0] == "organic":
                    organic_data = item["content"][1]
                    if "link" in organic_data and organic_data["link"][0] == "Some":
                        link_data = organic_data["link"][1]
                        result_item = {
                            "title": link_data.get("title", ""),
                            "url": link_data.get("url", [None, {}])[1].get("url", ""),
                            "position": item.get("pos", 0)
                        }
                        
                        # 添加指标数据（如果有）
                        if "metrics" in link_data and link_data["metrics"]:
                            metrics = link_data["metrics"]
                            result_item.update({
                                "domainRating": metrics.get("domainRating", 0),
                                "urlRating": metrics.get("urlRating", 0),
                                "traffic": metrics.get("traffic", 0),
                                "keywords": metrics.get("keywords", 0),
                                "topKeyword": metrics.get("topKeyword", ""),
                                "topVolume": metrics.get("topVolume", 0)
                            })
                        
                        serp_results.append(result_item)
            
            result["serp"]["results"] = serp_results
        
        return result
    except Exception:
        return None
