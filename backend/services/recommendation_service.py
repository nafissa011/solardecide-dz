"""Zone recommendation service — scoring and ranking for solar potential."""

import logging
import time
from typing import List, Dict, Any, Optional

import numpy as np

from ai_zone_recommendation import ZoneRecommendationComponent
from data_engine import DataEngine
from schemas import ZoneRecommendationRequest, ZoneRecommendationResponse, validate_wilaya_code
from services.zone_model_service import ZoneModelService

logger = logging.getLogger(__name__)


class RecommendationService:

    def __init__(self, data_engine: DataEngine, model_service: Optional[ZoneModelService] = None):
        self.data_engine = data_engine
        self.component = ZoneRecommendationComponent(data_engine)
        self.model_service = model_service
        if model_service:
            logger.info("RecommendationService initialized with ML model service")
        else:
            logger.info("RecommendationService initialized (deterministic scoring only)")

    def get_wilaya_zones_sorted(self, wilaya_code: int) -> List[Dict[str, Any]]:
        """Returns all zones for a wilaya sorted by score desc, with rank added."""
        wilaya = self.data_engine.get_wilaya_detail(wilaya_code)
        if not wilaya:
            logger.warning(f"Wilaya {wilaya_code} not found")
            return []

        zones = self.data_engine.get_zones(wilaya_name=wilaya.get("wilaya_name"))

        scored_zones = []
        for zone in zones:
            if self.model_service and self._should_use_ml_model(zone):
                try:
                    zone["score"] = self._score_zone_with_ml(zone)
                except Exception as e:
                    logger.warning(f"ML scoring failed for {zone.get('commune_name')}, using deterministic: {e}")
                    zone["score"] = self.component._compute_zone_score(zone)
            else:
                zone["score"] = self.component._compute_zone_score(zone)

            if "recommendation" not in zone:
                score = zone["score"]
                zone["recommendation"] = (
                    "build" if score >= 80 else
                    "study" if score >= 60 else "wait"
                )

            scored_zones.append(zone)

        zones_sorted = sorted(scored_zones, key=lambda z: z.get("score", 0), reverse=True)
        for i, zone in enumerate(zones_sorted):
            zone["rank"] = i + 1

        return zones_sorted

    def recommend_zones_for_capacity(
        self,
        wilaya_code: int,
        target_capacity_mw: float,
        objective: str = "utility"
    ) -> ZoneRecommendationResponse:
        """
        Returns zones ranked by score that cumulatively meet target_capacity_mw.
        Uses ML scoring when model_service is available, otherwise delegates to component.
        The last selected zone may be partially allocated to exactly hit the target.
        """
        start_time = time.time()
        logger.info(
            f"Zone recommendation started: wilaya={wilaya_code}, "
            f"capacity={target_capacity_mw}MW, objective={objective}"
        )

        validate_wilaya_code(wilaya_code)

        request = ZoneRecommendationRequest(
            wilaya_code=wilaya_code,
            target_capacity_mw=target_capacity_mw,
            objective=objective
        )

        if not self.model_service:
            response = self.component.recommend_zones(request)
            processing_time = (time.time() - start_time) * 1000
            logger.info(
                f"Recommendation complete: {len(response.recommended_zones)} zones "
                f"in {processing_time:.2f}ms"
            )
            return response

        wilaya_data = self.data_engine.get_wilaya_detail(wilaya_code)
        if not wilaya_data:
            raise ValueError(f"Wilaya {wilaya_code} not found")

        zones = self.data_engine.get_zones(wilaya_name=wilaya_data['wilaya_name'])
        if not zones:
            logger.warning(f"No zones found for wilaya {wilaya_code}")
            return ZoneRecommendationResponse(
                wilaya_code=request.wilaya_code,
                wilaya_name=wilaya_data['wilaya_name'],
                wilaya_score=0.0,
                target_capacity_mw=request.target_capacity_mw,
                recommended_zones=[],
                summary_statistics={
                    'total_zones_available': 0,
                    'zones_selected': 0,
                    'cumulative_potential_mw': 0.0,
                    'average_score': 0.0,
                    'best_zone': None,
                },
                processing_time_ms=(time.time() - start_time) * 1000
            )

        scored_zones = []
        for zone in zones:
            if self._should_use_ml_model(zone):
                try:
                    zone['score'] = self._score_zone_with_ml(zone)
                except Exception as e:
                    logger.warning(f"ML scoring failed for {zone.get('commune_name')}, using deterministic: {e}")
                    zone["score"] = self.component._compute_zone_score(zone)
            else:
                zone["score"] = self.component._compute_zone_score(zone)
            scored_zones.append(zone)

        scored_zones.sort(key=lambda z: z['score'], reverse=True)
        for i, zone in enumerate(scored_zones):
            zone['rank'] = i + 1

        # Greedily fill capacity; partially allocate the last zone if needed
        selected_zones = []
        cumulative_capacity = 0.0

        for zone in scored_zones:
            zone_capacity = zone.get('potential_mw', 1.0)
            if cumulative_capacity + zone_capacity <= target_capacity_mw:
                selected_zones.append(zone)
                cumulative_capacity += zone_capacity
            else:
                remaining = target_capacity_mw - cumulative_capacity
                if remaining > 0:
                    partial_zone = zone.copy()
                    partial_zone['allocated_capacity_mw'] = remaining
                    partial_zone['utilization'] = remaining / zone_capacity
                    selected_zones.append(partial_zone)
                break

        wilaya_score = self._get_wilaya_score(request.wilaya_code)
        summary_statistics = {
            'total_zones_available': len(scored_zones),
            'zones_selected':        len(selected_zones),
            'cumulative_potential_mw': round(cumulative_capacity, 2),
            'average_score': round(np.mean([z['score'] for z in selected_zones]) if selected_zones else 0, 2),
            'best_zone': selected_zones[0].get('commune_name') if selected_zones else None,
        }

        response_zones = []
        for zone in selected_zones:
            stats = self._get_zone_statistics(zone)
            response_zones.append({
                'rank':               stats['rank'],
                'commune_name':       zone.get('commune_name', 'Unknown'),
                'score':              stats['score'],
                'mean_ghi':           stats['mean_ghi'],
                'mean_ghi_annual':    round(zone.get('mean_ghi', 0.0) * 8760.0, 2),
                'mean_dni':           float(zone.get('mean_dni', 0.0)),
                'mean_dhi':           float(zone.get('mean_dhi', 0.0)),
                'mean_t2m':           stats['temperature'],
                'mean_ws10m':         float(zone.get('mean_ws10m', 0.0)),
                'mean_clearness':     stats['clearness'],
                'latitude':           zone.get('latitude', 0.0),
                'longitude':          zone.get('longitude', 0.0),
                'potential_mw':       round(zone.get('potential_mw', 0.0), 2),
                'capacity_factor':    stats['capacity_factor'],
                'variability':        round(zone.get('variability', 0.0), 3),
                'recommendation':     'build' if stats['score'] >= 80 else 'study' if stats['score'] >= 60 else 'wait',
                'climate':            str(zone.get('climate', 'Unknown')),
                'allocated_capacity_mw': zone.get('allocated_capacity_mw', zone.get('potential_mw', 0.0)),
                'utilization':        round(zone.get('utilization', 1.0), 3),
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

    def _should_use_ml_model(self, zone: Dict[str, Any]) -> bool:
        model_type = zone.get("model_type")
        if not model_type:
            return False
        available = self.model_service.get_available_models() if self.model_service else []
        return model_type in available

    def _score_zone_with_ml(self, zone: Dict[str, Any]) -> float:
        model_type = zone.get("model_type")
        features = self.model_service.extract_features(zone)
        return self.model_service.predict(model_type, features)

    def _get_wilaya_score(self, wilaya_code: int) -> float:
        wilayas = self.data_engine.get_wilayas_summary()
        match = next((w for w in wilayas if int(w.get("wilaya_code", 0)) == wilaya_code), None)
        return float(match.get("score", 0.0)) if match else 0.0

    def _get_zone_statistics(self, zone_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mean_ghi":        round(zone_data.get("mean_ghi", 0), 2),
            "peak_ghi":        round(zone_data.get("peak_ghi", 0), 2),
            "sunshine_hours":  round(zone_data.get("sunshine_hours", 0), 3),
            "clearness":       round(zone_data.get("clearness", 0), 3),
            "low_variability": round(1 - zone_data.get("variability", 0), 3),
            "temperature":     round(zone_data.get("temperature", 25), 1),
            "wind_speed":      round(zone_data.get("wind_speed", 5), 1),
            "capacity_factor": round(zone_data.get("capacity_factor", 0.25), 3),
            "score":           round(zone_data.get("score", 0), 2),
            "rank":            zone_data.get("rank", 0),
        }

    def get_wilaya_statistics(self, wilaya_code: int) -> Dict[str, Any]:
        """Returns wilaya info, top 15 zones, and aggregated score/GHI statistics."""
        validate_wilaya_code(wilaya_code)

        wilaya = self.data_engine.get_wilaya_detail(wilaya_code)
        if not wilaya:
            raise ValueError(f"Wilaya {wilaya_code} not found")

        zones = self.get_wilaya_zones_sorted(wilaya_code)
        scores = [z["score"] for z in zones]
        mean_ghi_vals = [z["mean_ghi"] for z in zones]

        return {
            "wilaya": wilaya,
            "zones":  zones[:15],
            "statistics": {
                "total_zones":    len(zones),
                "avg_score":      round(np.mean(scores), 2) if scores else 0,
                "best_score":     round(np.max(scores), 2) if scores else 0,
                "worst_score":    round(np.min(scores), 2) if scores else 0,
                "score_std":      round(np.std(scores), 2) if scores else 0,
                "avg_ghi_annual": round(np.mean(mean_ghi_vals) * 8760, 0) if mean_ghi_vals else 0,
                "excellent_zones": sum(1 for s in scores if s >= 80),
                "good_zones":      sum(1 for s in scores if 60 <= s < 80),
                "study_zones":     sum(1 for s in scores if 40 <= s < 60),
            }
        }