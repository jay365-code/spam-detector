import glob
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from metrics import calculate_advanced_metrics
from logging_config import get_logger

from logging_config import get_logger
import string

logger = get_logger(__name__)

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

# --- Models ---

class FolderListResponse(BaseModel):
    current_path: str
    folders: List[str]
    is_root: bool
    parent_path: Optional[str] = None

class MonitorTrendResponse(BaseModel):
    dates: List[str]
    kappas: List[float]
    fn_rates: List[float]
    daily_summaries: List[Dict[str, Any]]

class MonitorDailyResponse(BaseModel):
    date: str
    summary: Dict[str, Any]
    source_breakdown: List[Dict[str, Any]]
    diffs: List[Dict[str, Any]]

# --- Logic ---

def parse_filename(filename: str) -> Optional[Dict[str, str]]:
    """
    파일명에서 날짜와 소스(A/B/C)를 추출합니다.
    예: 일별비교_20260101_A.json -> {'date': '20260101', 'source': 'A'}
    """
    match = re.search(r'(\d{8})_([A-Za-z0-9]+)', filename)
    if match:
        return {'date': match.group(1), 'source': match.group(2)}
    return None

def load_json_files(folder_path: str) -> List[Dict[str, Any]]:
    """지정된 폴더에서 JSON 파일들을 로드합니다."""
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder_path}")

    files = glob.glob(os.path.join(folder_path, "*.json"))
    loaded_data = []

    for fpath in files:
        try:
            fname = os.path.basename(fpath)
            meta = parse_filename(fname)
            if not meta:
                continue

            with open(fpath, 'r', encoding='utf-8') as f:
                content = json.load(f)
                
            loaded_data.append({
                'date': meta['date'],
                'source': meta['source'],
                'filename': fname,
                'content': content
            })
        except Exception as e:
            logger.error(f"Error loading {fpath}: {e}")
            continue
            
    return loaded_data

@router.get("/trend", response_model=MonitorTrendResponse)
async def get_trend(folder_path: str = Query(..., description="Absolute path to JSON folder")):
    """
    지정된 폴더의 JSON 파일들을 로드하여 일별 추세 데이터를 반환합니다.
    """
    data = load_json_files(folder_path)
    if not data:
        return MonitorTrendResponse(dates=[], kappas=[], fn_rates=[], daily_summaries=[])

    # Group by date
    grouped = {}
    for item in data:
        date = item['date']
        if date not in grouped:
            grouped[date] = []
        grouped[date].append(item)

    daily_summaries = []
    
    # Process each date
    for date, items in grouped.items():
        # Aggregate counts
        agg_tp = 0
        agg_tn = 0
        agg_fp = 0
        agg_fn = 0
        total_matched = 0
        
        sources = []

        for item in items:
            summary = item['content'].get('summary', {})
            # Use safe get with default 0
            tp = summary.get('tp', 0)
            tn = summary.get('tn', 0)
            fp = summary.get('fp', 0)
            fn = summary.get('fn', 0)
            matched = tp + tn + fp + fn # Recalculate matched from confusion matrix
            
            agg_tp += tp
            agg_tn += tn
            agg_fp += fp
            agg_fn += fn
            total_matched += matched
            
            sources.append(item['source'])

        # Recalculate Daily KPI
        metrics = calculate_advanced_metrics(agg_tp, agg_tn, agg_fp, agg_fn, total_matched)
        
        # FN Rate
        fn_rate = agg_fn / (agg_tp + agg_fn) if (agg_tp + agg_fn) > 0 else 0.0

        daily_summaries.append({
            "date": date,
            "sources": sorted(sources),
            "tp": agg_tp,
            "tn": agg_tn,
            "fp": agg_fp,
            "fn": agg_fn,
            "accuracy": metrics['accuracy'],
            "kappa": metrics['kappa'],
            "mcc": metrics['mcc'],
            "fn_rate": round(fn_rate, 4),
            "primary_status": metrics['primary_status'],
            "primary_color": metrics['primary_color']
        })

    # Sort by date
    daily_summaries.sort(key=lambda x: x['date'])

    return MonitorTrendResponse(
        dates=[d['date'] for d in daily_summaries],
        kappas=[d['kappa'] for d in daily_summaries],
        fn_rates=[d['fn_rate'] for d in daily_summaries],
        daily_summaries=daily_summaries
    )

@router.get("/day/{date}", response_model=MonitorDailyResponse)
async def get_daily_detail(date: str, folder_path: str = Query(..., description="Absolute path to JSON folder")):
    """
    특정 날짜의 상세 데이터를 반환합니다 (소스별 내역, 통합 Diffs).
    """
    data = load_json_files(folder_path)
    target_items = [d for d in data if d['date'] == date]
    
    if not target_items:
        raise HTTPException(status_code=404, detail=f"No data found for date: {date}")

    # Aggregate Diffs & Source Breakdown
    all_diffs = []
    source_breakdown = []
    
    agg_tp = 0
    agg_tn = 0
    agg_fp = 0
    agg_fn = 0
    total_matched = 0

    for item in target_items:
        src = item['source']
        content = item['content']
        summary = content.get('summary', {})
        diffs = content.get('diffs', [])

        # Source breakdown
        s_metrics = calculate_advanced_metrics(
            summary.get('tp', 0), 
            summary.get('tn', 0), 
            summary.get('fp', 0), 
            summary.get('fn', 0), 
            summary.get('matched', 0)
        )
        
        source_breakdown.append({
            "source": src,
            "tp": summary.get('tp', 0),
            "tn": summary.get('tn', 0),
            "fp": summary.get('fp', 0),
            "fn": summary.get('fn', 0),
            "kappa": s_metrics['kappa'],
            "accuracy": s_metrics['accuracy']
        })

        # Aggregation for daily summary
        agg_tp += summary.get('tp', 0)
        agg_tn += summary.get('tn', 0)
        agg_fp += summary.get('fp', 0)
        agg_fn += summary.get('fn', 0)
        total_matched += summary.get('matched', 0)

        # Collect diffs with source tag
        for d in diffs:
            d['source'] = src
            all_diffs.append(d)

    # Recalculate Daily Total Metrics
    daily_metrics = calculate_advanced_metrics(agg_tp, agg_tn, agg_fp, agg_fn, total_matched)
    
    final_summary = {
        "tp": agg_tp,
        "tn": agg_tn,
        "fp": agg_fp,
        "fn": agg_fn,
        "total": total_matched,
        **daily_metrics
    }

    return MonitorDailyResponse(
        date=date,
        summary=final_summary,
        source_breakdown=source_breakdown,
        diffs=all_diffs
    )

@router.get("/fs/list", response_model=FolderListResponse)
async def list_folders(path: Optional[str] = Query(None, description="Path to list folders from")):
    """
    서버의 폴더 목록을 반환합니다.
    path가 없으면 드라이브 목록(Windows)을 반환합니다.
    """
    try:
        folders = []
        is_root = False
        current_path = path if path else ""
        parent_path = None

        if not path:
            # List Drives (Windows)
            # Linux/Mac would be just "/"
            if os.name == 'nt':
                drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:")]
                folders = drives
                is_root = True
                current_path = ""
            else:
                current_path = "/"
                parent_path = None
                # List root folders
                with os.scandir("/") as it:
                    for entry in it:
                        if entry.is_dir() and not entry.name.startswith('.'):
                            folders.append(entry.path)
        else:
            # Check if path exists
            if not os.path.exists(path):
                raise HTTPException(status_code=400, detail="Path does not exist")
            
            if not os.path.isdir(path):
                raise HTTPException(status_code=400, detail="Path is not a directory")

            # Get Parent
            parent_path = os.path.dirname(path)
            if parent_path == path: # Root
                parent_path = "" # Go back to drive selection if at root

            # List subdirectories
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith('.'):
                        folders.append(entry.name) # Just key name, user will append
            
            folders.sort()

        return FolderListResponse(
            current_path=current_path,
            folders=folders,
            is_root=is_root,
            parent_path=parent_path
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
