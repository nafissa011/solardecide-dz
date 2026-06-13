import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from config import SCORE_WEIGHTS, GHI_THRESH
from data_engine import DataEngine
from schemas import ZoneRecommendationRequest, ZoneRecommendationResponse, ZoneScore

logger = logging.getLogger(__name__)


@dataclass
class ZoneStats:
    mean_ghi: float
    peak_ghi: float
    sunshine_hours: float
    clearness: float
    low_variability: float
    temperature: float
    wind_speed: float
    capacity_factor: float
    score: float
    rank: int


class ZoneRecommendationComponent:

    def __init__(self, data_engine: DataEngine):
        self.data_engine = data_engine
        self._load_data_pipeline()
        logger.info("ZoneRecommendationComponent initialized")

    def _load_data_pipeline(self):
        try:
            scores_path = Path(__file__).parent.parent / "data" / "results" / "wilaya_solar_scores.csv"
            if scores_path.exists():
                self.wilaya_scores = pd.read_csv(scores_path)
                logger.info("Wilaya scores loaded from data pipeline")
            else:
                logger.warning(f"Wilaya scores file not found at {scores_path}, will compute on-demand")
                self.wilaya_scores = None
        except Exception as e:
            logger.warning(f"Could not load wilaya scores: {e}, will compute on-demand")
            self.wilaya_scores = None

    def _get_wilaya_score(self, wilaya_code: int) -> float:
        wilayas = self.data_engine.get_wilayas_summary()
        match = next((w for w in wilayas if int(w.get('wilaya_code', 0)) == wilaya_code), None)
        return float(match.get('score', 0.0)) if match else 0.0

    def _compute_zone_score(self, zone_data: Dict[str, Any]) -> float:
        """
        Expects pre-normalized scores (s_mean_ghi, s_peak_ghi, etc.) from DataEngine.
        Per-zone normalization would produce NaN on single-element sets.
        """
        try:
            s_mean_ghi  = max(0.0, min(1.0, float(zone_data.get('s_mean_ghi', 0))))
            s_peak_ghi  = max(0.0, min(1.0, float(zone_data.get('s_peak_ghi', 0))))
            s_sunshine  = max(0.0, min(1.0, float(zone_data.get('s_sunshine_hours', 0))))
            s_clearness = max(0.0, min(1.0, float(zone_data.get('s_clearness', 0))))
            s_low_var   = max(0.0, min(1.0, float(zone_data.get('s_low_variability', 0))))

            score = (
                s_mean_ghi  * SCORE_WEIGHTS['mean_ghi'] +
                s_peak_ghi  * SCORE_WEIGHTS['peak_ghi'] +
                s_sunshine  * SCORE_WEIGHTS['sunshine_hours'] +
                s_clearness * SCORE_WEIGHTS['clearness'] +
                s_low_var   * SCORE_WEIGHTS['low_variability']
            ) * 100

            return round(score, 2)

        except Exception as e:
            logger.error(f"Error computing zone score: {e}")
            return 0.0

    def _get_zone_statistics(self, zone_data: Dict[str, Any]) -> ZoneStats:
        return ZoneStats(
            mean_ghi=round(zone_data.get('mean_ghi', 0), 2),
            peak_ghi=round(zone_data.get('peak_ghi', 0), 2),
            sunshine_hours=round(zone_data.get('sunshine_hours', 0), 3),
            clearness=round(zone_data.get('clearness', 0), 3),
            low_variability=round(1 - zone_data.get('variability', 0), 3),  # invert: lower variability = better
            temperature=round(zone_data.get('temperature', 25), 1),
            wind_speed=round(zone_data.get('wind_speed', 5), 1),
            capacity_factor=round(zone_data.get('capacity_factor', 0.25), 3),
            score=round(zone_data.get('score', 0), 2),
            rank=zone_data.get('rank', 0)
        )

    def recommend_zones(self, request: ZoneRecommendationRequest) -> ZoneRecommendationResponse:
        start_time = time.time()
        logger.info(f"Zone recommendation request: wilaya={request.wilaya_code}, capacity={request.target_capacity_mw}MW")

        try:
            if not (1 <= request.wilaya_code <= 58):
                raise ValueError(f"Invalid wilaya code: {request.wilaya_code}")
            if request.target_capacity_mw <= 0:
                raise ValueError(f"Invalid capacity: {request.target_capacity_mw}")

            wilaya_data = self.data_engine.get_wilaya_detail(request.wilaya_code)
            if not wilaya_data:
                raise ValueError(f"Wilaya {request.wilaya_code} not found")

            zones = self.data_engine.get_zones(wilaya_name=wilaya_data['wilaya_name'])
            if not zones:
                logger.warning(f"No zones found for wilaya {request.wilaya_code}")
                return ZoneRecommendationResponse(
                    wilaya_code=request.wilaya_code,
                    wilaya_name=wilaya_data['wilaya_name'],
                    wilaya_score=0.0,
                    target_capacity_mw=request.target_capacity_mw,
                    recommended_zones=[],
                    summary_statistics={
                        'total_zones_available': 0,
                        'zones_shown': 0,
                        'cumulative_potential_mw': 0.0,
                        'average_score': 0.0,
                        'best_zone': None,
                    },
                    processing_time_ms=(time.time() - start_time) * 1000
                )

            scored_zones = sorted(
                [{**z, 'score': self._compute_zone_score(z)} for z in zones],
                key=lambda z: z['score'],
                reverse=True
            )
            for i, zone in enumerate(scored_zones):
                zone['rank'] = i + 1

            # Greedy capacity fill: pick top zones until target is met, split the last one if needed
            selected_zones = []
            cumulative_capacity = 0.0

            for zone in scored_zones:
                zone_capacity = zone.get('potential_mw', 1.0)  # default 1 MW when field is missing
                remaining = request.target_capacity_mw - cumulative_capacity
                if cumulative_capacity + zone_capacity <= request.target_capacity_mw:
                    selected_zones.append(zone)
                    cumulative_capacity += zone_capacity
                elif remaining > 0:
                    partial_zone = zone.copy()
                    partial_zone['allocated_capacity_mw'] = remaining
                    partial_zone['utilization'] = remaining / zone_capacity
                    selected_zones.append(partial_zone)
                    cumulative_capacity += remaining
                    break
                else:
                    break

            wilaya_score = self._get_wilaya_score(request.wilaya_code)
            summary_statistics = {
                'total_zones_available': len(scored_zones),
                'zones_selected': len(selected_zones),
                'cumulative_potential_mw': round(cumulative_capacity, 2),
                'average_score': round(np.mean([z['score'] for z in selected_zones]) if selected_zones else 0, 2),
                'best_zone': selected_zones[0].get('commune_name') if selected_zones else None,
            }

            response_zones = []
            for zone in selected_zones:
                stats = self._get_zone_statistics(zone)
                response_zones.append({
                    'rank': stats.rank,
                    'commune_name': zone.get('commune_name', 'Unknown'),
                    'score': stats.score,
                    'mean_ghi': stats.mean_ghi,
                    'mean_ghi_annual': round(zone.get('mean_ghi', 0.0) * 8760.0, 2),
                    'mean_dni': float(zone.get('mean_dni', 0.0)),
                    'mean_dhi': float(zone.get('mean_dhi', 0.0)),
                    'mean_t2m': stats.temperature,
                    'mean_ws10m': float(zone.get('mean_ws10m', 0.0)),
                    'mean_clearness': stats.clearness,
                    'latitude': zone.get('latitude', 0.0),
                    'longitude': zone.get('longitude', 0.0),
                    'potential_mw': round(zone.get('potential_mw', 0.0), 2),
                    'capacity_factor': stats.capacity_factor,
                    'variability': round(zone.get('variability', 0.0), 3),
                    'recommendation': 'build' if stats.score >= 80 else 'study' if stats.score >= 60 else 'wait',
                    'climate': str(zone.get('climate', 'Unknown')),
                    'allocated_capacity_mw': zone.get('allocated_capacity_mw', zone.get('potential_mw', 0.0)),
                    'utilization': round(zone.get('utilization', 1.0), 3)
                })

            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Zone recommendation completed: {len(response_zones)} zones selected, {processing_time:.1f}ms")

            return ZoneRecommendationResponse(
                wilaya_code=request.wilaya_code,
                wilaya_name=wilaya_data['wilaya_name'],
                wilaya_score=wilaya_score,
                target_capacity_mw=request.target_capacity_mw,
                recommended_zones=response_zones,
                summary_statistics=summary_statistics,
                processing_time_ms=processing_time
            )

        except Exception as e:
            logger.error(f"Zone recommendation failed: {e}", exc_info=True)
            raise

    def get_wilaya_statistics(self, wilaya_code: int) -> Dict[str, Any]:
        try:
            wilaya_data = self.data_engine.get_wilaya_detail(wilaya_code)
            if not wilaya_data:
                raise ValueError(f"Wilaya {wilaya_code} not found")

            zones = self.data_engine.get_zones(wilaya_name=wilaya_data['wilaya_name'])

            if zones:
                ghi_values  = [z.get('mean_ghi', 0)    for z in zones if z.get('mean_ghi')]
                temp_values = [z.get('temperature', 25) for z in zones if z.get('temperature')]
                wind_values = [z.get('wind_speed', 5)   for z in zones if z.get('wind_speed')]

                stats = {
                    'mean_ghi':            round(np.mean(ghi_values), 2)  if ghi_values  else 0,
                    'peak_ghi':            round(np.max(ghi_values), 2)   if ghi_values  else 0,
                    'temperature':         round(np.mean(temp_values), 1) if temp_values else 25,
                    'wind_speed':          round(np.mean(wind_values), 1) if wind_values else 5,
                    'total_zones':         len(zones),
                    'high_potential_zones': len([z for z in zones if self._compute_zone_score(z) >= 80])
                }
            else:
                stats = {
                    'mean_ghi': 0, 'peak_ghi': 0,
                    'temperature': 25, 'wind_speed': 5,
                    'total_zones': 0, 'high_potential_zones': 0
                }

            return {
                'wilaya_code': wilaya_code,
                'wilaya_name': wilaya_data['wilaya_name'],
                'statistics': stats
            }

        except Exception as e:
            logger.error(f"Failed to get wilaya statistics: {e}")
            raise