"""
Creacion y agendado de workouts en Garmin Connect.

Usa los helpers nativos de garminconnect.workout para garantizar
el formato correcto que acepta la API de Garmin.
"""
import datetime
import logging
import json

from garminconnect.workout import (
    RunningWorkout,
    CyclingWorkout,
    WorkoutSegment,
    ExecutableStep,
    RepeatGroup,
    TargetType,
    ConditionType,
    StepType,
    create_warmup_step,
    create_interval_step,
    create_recovery_step,
    create_cooldown_step,
    create_repeat_group,
)
from garmin_client import get_client

logger = logging.getLogger(__name__)

# ---------- Targets con el formato correcto que acepta Garmin ----------

def _hr_zone_target(zone: int) -> dict:
    """Target de zona de FC usando las claves correctas de Garmin."""
    return {
        "workoutTargetTypeId": TargetType.HEART_RATE_ZONE,
        "workoutTargetTypeKey": "heart.rate.zone",
        "displayOrder": 1,
        "targetValueOne": float(zone),
        "targetValueTwo": float(zone),
    }


def _no_target() -> dict:
    return {
        "workoutTargetTypeId": TargetType.NO_TARGET,
        "workoutTargetTypeKey": "no.target",
        "displayOrder": 1,
    }


def _distance_end_condition(meters: float) -> dict:
    return {
        "conditionTypeId": ConditionType.DISTANCE,
        "conditionTypeKey": "distance",
        "displayOrder": 2,
        "displayable": True,
    }


# ---------- Constructores de steps ----------

def warmup_step(step_order: int, duration_seconds: float, hr_zone: int = 2) -> ExecutableStep:
    return ExecutableStep(
        stepOrder=step_order,
        stepType={
            "stepTypeId": StepType.WARMUP,
            "stepTypeKey": "warmup",
            "displayOrder": 1,
        },
        endCondition={
            "conditionTypeId": ConditionType.TIME,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        },
        endConditionValue=float(duration_seconds),
        targetType=_hr_zone_target(hr_zone),
    )


def cooldown_step(step_order: int, duration_seconds: float, hr_zone: int = 1) -> ExecutableStep:
    return ExecutableStep(
        stepOrder=step_order,
        stepType={
            "stepTypeId": StepType.COOLDOWN,
            "stepTypeKey": "cooldown",
            "displayOrder": 2,
        },
        endCondition={
            "conditionTypeId": ConditionType.TIME,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        },
        endConditionValue=float(duration_seconds),
        targetType=_hr_zone_target(hr_zone),
    )


def steady_step(step_order: int, duration_seconds: float, hr_zone: int) -> ExecutableStep:
    """Paso continuo por tiempo en una zona de FC."""
    return ExecutableStep(
        stepOrder=step_order,
        stepType={
            "stepTypeId": StepType.INTERVAL,
            "stepTypeKey": "interval",
            "displayOrder": 3,
        },
        endCondition={
            "conditionTypeId": ConditionType.TIME,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        },
        endConditionValue=float(duration_seconds),
        targetType=_hr_zone_target(hr_zone),
    )


def interval_distance_step(step_order: int, distance_meters: float, hr_zone: int = 5) -> ExecutableStep:
    """Intervalo por distancia en una zona de FC."""
    return ExecutableStep(
        stepOrder=step_order,
        stepType={
            "stepTypeId": StepType.INTERVAL,
            "stepTypeKey": "interval",
            "displayOrder": 3,
        },
        endCondition=_distance_end_condition(distance_meters),
        endConditionValue=float(distance_meters),
        targetType=_hr_zone_target(hr_zone),
    )


def recovery_time_step(step_order: int, duration_seconds: float) -> ExecutableStep:
    """Recuperación por tiempo en Z1."""
    return ExecutableStep(
        stepOrder=step_order,
        stepType={
            "stepTypeId": StepType.RECOVERY,
            "stepTypeKey": "recovery",
            "displayOrder": 4,
        },
        endCondition={
            "conditionTypeId": ConditionType.TIME,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        },
        endConditionValue=float(duration_seconds),
        targetType=_hr_zone_target(1),
    )


# ---------- Plantillas de workouts ----------

def build_easy_run(name: str, total_minutes: int, description: str = "") -> RunningWorkout:
    """Rodaje suave continuo en Z2."""
    warmup_secs = 600.0
    cooldown_secs = 600.0
    main_secs = max((total_minutes * 60) - warmup_secs - cooldown_secs, 600.0)

    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=int(total_minutes * 60),
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
            workoutSteps=[
                warmup_step(1, warmup_secs, hr_zone=2),
                steady_step(2, main_secs, hr_zone=2),
                cooldown_step(3, cooldown_secs, hr_zone=1),
            ]
        )]
    )


def build_tempo_run(name: str, warmup_min: int, tempo_min: int,
                    cooldown_min: int, description: str = "") -> RunningWorkout:
    """Tempo continuo en Z4."""
    total = (warmup_min + tempo_min + cooldown_min) * 60
    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=total,
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
            workoutSteps=[
                warmup_step(1, warmup_min * 60, hr_zone=2),
                steady_step(2, tempo_min * 60, hr_zone=4),
                cooldown_step(3, cooldown_min * 60, hr_zone=1),
            ]
        )]
    )


def build_interval_run(name: str, warmup_min: int, interval_distance_m: int,
                       repetitions: int, recovery_seconds: int, cooldown_min: int,
                       interval_hr_zone: int = 5, description: str = "") -> RunningWorkout:
    """Intervalos por distancia (ej: 4x1000m)."""
    interval_steps = []
    order = 1
    for i in range(repetitions):
        interval_steps.append(interval_distance_step(order, float(interval_distance_m), hr_zone=interval_hr_zone))
        order += 1
        if i < repetitions - 1:
            interval_steps.append(recovery_time_step(order, float(recovery_seconds)))
            order += 1

    rep_group = create_repeat_group(repetitions, interval_steps, step_order=2)
    estimated = int((warmup_min + cooldown_min) * 60 + repetitions * (interval_distance_m / 3.5 + recovery_seconds))

    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=estimated,
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
            workoutSteps=[
                warmup_step(1, warmup_min * 60, hr_zone=2),
                rep_group,
                cooldown_step(3, cooldown_min * 60, hr_zone=1),
            ]
        )]
    )


def build_long_run(name: str, total_minutes: int, description: str = "") -> RunningWorkout:
    """Tirada larga en Z2 con bloque final en Z3."""
    warmup_secs = 600.0
    cooldown_secs = 600.0
    z3_secs = float(min(total_minutes * 60 * 0.2, 1200))
    main_secs = max((total_minutes * 60) - warmup_secs - z3_secs - cooldown_secs, 600.0)

    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=int(total_minutes * 60),
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
            workoutSteps=[
                warmup_step(1, warmup_secs, hr_zone=2),
                steady_step(2, main_secs, hr_zone=2),
                steady_step(3, z3_secs, hr_zone=3),
                cooldown_step(4, cooldown_secs, hr_zone=1),
            ]
        )]
    )


def build_easy_bike(name: str, total_minutes: int, description: str = "") -> CyclingWorkout:
    """Rodaje suave de ciclismo en Z2."""
    warmup_secs = 600.0
    cooldown_secs = 600.0
    main_secs = max((total_minutes * 60) - warmup_secs - cooldown_secs, 600.0)

    return CyclingWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=int(total_minutes * 60),
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 1},
            workoutSteps=[
                warmup_step(1, warmup_secs, hr_zone=2),
                steady_step(2, main_secs, hr_zone=2),
                cooldown_step(3, cooldown_secs, hr_zone=1),
            ]
        )]
    )


# ---------- Upload / schedule / consulta ----------

def upload_and_schedule_workout(workout_obj, date_str: str) -> dict:
    """Sube un workout a Garmin Connect y lo agenda en la fecha indicada."""
    client = get_client()
    workout_dict = workout_obj.to_dict()
    logger.info("Subiendo workout: %s", json.dumps(workout_dict, indent=2))

    try:
        uploaded = client.upload_workout(workout_dict)
        logger.info("Respuesta upload: %s", uploaded)
    except Exception as e:
        logger.error("Error en upload_workout: %s", str(e))
        return {"error": f"Error al subir workout a Garmin: {str(e)}"}

    workout_id = uploaded.get("workoutId") if isinstance(uploaded, dict) else None
    if not workout_id:
        return {"error": "No se pudo obtener el workoutId", "raw": str(uploaded)}

    try:
        scheduled = client.schedule_workout(workout_id, date_str)
        logger.info("Respuesta schedule: %s", scheduled)
    except Exception as e:
        logger.error("Error en schedule_workout: %s", str(e))
        return {"error": f"Workout subido (id: {workout_id}) pero falló al agendarlo: {str(e)}"}

    scheduled_id = scheduled.get("scheduledWorkoutId") if isinstance(scheduled, dict) else None

    return {
        "workout_id": workout_id,
        "scheduled_id": scheduled_id,
        "name": workout_obj.workoutName,
        "date": date_str,
        "status": "agendado",
    }


def get_scheduled_workouts_for_week(date_str: str = None) -> list:
    """Workouts agendados en Garmin para el mes de la fecha indicada."""
    client = get_client()
    d = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    try:
        data = client.get_scheduled_workouts(d.year, d.month)
        return data if isinstance(data, list) else [data]
    except Exception as e:
        return [{"error": str(e)}]


def delete_scheduled_workout(scheduled_workout_id: str) -> dict:
    """Borra un workout del calendario de Garmin por su scheduled_id."""
    client = get_client()
    try:
        client.unschedule_workout(scheduled_workout_id)
        return {"status": "borrado", "scheduled_id": scheduled_workout_id}
    except Exception as e:
        return {"error": str(e)}
