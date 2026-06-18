"""
Creacion y agendado de workouts en Garmin Connect.

Permite que Claude construya sesiones estructuradas (running, ciclismo,
natacion) con pasos reales (calentamiento, intervalos, recuperacion,
vuelta a la calma) y las agende en fechas especificas del calendario
de Garmin. Aparecen en el reloj como workouts guiados.

Zonas de FC asumidas (ajustar si el usuario tiene zonas personalizadas):
  Z1: < 60% FCmax  — recuperacion activa
  Z2: 60-70% FCmax — aerobico base
  Z3: 70-80% FCmax — aerobico moderado / tempo suave
  Z4: 80-90% FCmax — umbral / tempo duro
  Z5: > 90% FCmax  — VO2max / intervalos
"""
import datetime
from garminconnect.workout import (
    RunningWorkout,
    CyclingWorkout,
    SwimmingWorkout,
    WorkoutSegment,
    ExecutableStep,
    RepeatGroup,
    TargetType,
    ConditionType,
    create_warmup_step,
    create_interval_step,
    create_recovery_step,
    create_cooldown_step,
    create_repeat_group,
)
from garmin_client import get_client


# ---------- Helpers para construir targets ----------

def _hr_zone_target(zone: int) -> dict:
    """Target de zona de FC (1-5) para un paso."""
    return {
        "targetType": {"targetTypeId": TargetType.HEART_RATE_ZONE, "targetTypeKey": "heart.rate.zone"},
        "targetValueOne": zone,
        "targetValueTwo": zone,
    }


def _pace_target(min_pace_sec_per_km: float, max_pace_sec_per_km: float) -> dict:
    """Target de ritmo en segundos/km (velocidad en m/s internamente)."""
    # Garmin usa velocidad en m/s para SPEED_ZONE
    min_speed = 1000 / max_pace_sec_per_km  # ritmo mas lento = velocidad minima
    max_speed = 1000 / min_pace_sec_per_km  # ritmo mas rapido = velocidad maxima
    return {
        "targetType": {"targetTypeId": TargetType.SPEED_ZONE, "targetTypeKey": "speed.zone"},
        "targetValueOne": min_speed,
        "targetValueTwo": max_speed,
    }


def _no_target() -> dict:
    return {
        "targetType": {"targetTypeId": TargetType.NO_TARGET, "targetTypeKey": "no.target"},
    }


def _time_condition(seconds: float) -> dict:
    return {
        "conditionType": {"conditionTypeId": ConditionType.TIME, "conditionTypeKey": "time"},
        "conditionValue": seconds,
    }


def _distance_condition(meters: float) -> dict:
    return {
        "conditionType": {"conditionTypeId": ConditionType.DISTANCE, "conditionTypeKey": "distance"},
        "conditionValue": meters,
    }


# ---------- Constructores de steps con target ----------

def _step(step_order: int, step_type_key: str, step_type_id: int,
          duration_seconds: float = None, distance_meters: float = None,
          target: dict = None) -> ExecutableStep:
    """Constructor generico de un paso de workout."""
    end_cond = _distance_condition(distance_meters) if distance_meters else _time_condition(duration_seconds or 300)
    step = ExecutableStep(
        stepOrder=step_order,
        stepType={"stepTypeId": step_type_id, "stepTypeKey": step_type_key},
        endCondition=end_cond["conditionType"],
        endConditionValue=distance_meters or duration_seconds or 300,
    )
    if target:
        step.targetType = target["targetType"]
        step.targetValueOne = target.get("targetValueOne")
        step.targetValueTwo = target.get("targetValueTwo")
    return step


def warmup(step_order: int, duration_seconds: float, hr_zone: int = 2) -> ExecutableStep:
    s = create_warmup_step(duration_seconds, step_order)
    t = _hr_zone_target(hr_zone)
    s.targetType = t["targetType"]
    s.targetValueOne = t.get("targetValueOne")
    s.targetValueTwo = t.get("targetValueTwo")
    return s


def cooldown(step_order: int, duration_seconds: float, hr_zone: int = 1) -> ExecutableStep:
    s = create_cooldown_step(duration_seconds, step_order)
    t = _hr_zone_target(hr_zone)
    s.targetType = t["targetType"]
    s.targetValueOne = t.get("targetValueOne")
    s.targetValueTwo = t.get("targetValueTwo")
    return s


def interval_by_time(step_order: int, duration_seconds: float, hr_zone: int = None,
                     pace_range: tuple = None) -> ExecutableStep:
    """Intervalo por tiempo con zona de FC o rango de ritmo."""
    s = create_interval_step(duration_seconds, step_order)
    target = _hr_zone_target(hr_zone) if hr_zone else (_pace_target(*pace_range) if pace_range else _no_target())
    s.targetType = target["targetType"]
    s.targetValueOne = target.get("targetValueOne")
    s.targetValueTwo = target.get("targetValueTwo")
    return s


def interval_by_distance(step_order: int, distance_meters: float, hr_zone: int = None,
                          pace_range: tuple = None) -> ExecutableStep:
    """Intervalo por distancia con zona de FC o rango de ritmo."""
    target = _hr_zone_target(hr_zone) if hr_zone else (_pace_target(*pace_range) if pace_range else _no_target())
    return ExecutableStep(
        stepOrder=step_order,
        stepType={"stepTypeId": 3, "stepTypeKey": "interval"},
        endCondition={"conditionTypeId": ConditionType.DISTANCE, "conditionTypeKey": "distance"},
        endConditionValue=distance_meters,
        targetType=target["targetType"],
        targetValueOne=target.get("targetValueOne"),
        targetValueTwo=target.get("targetValueTwo"),
    )


def recovery_step(step_order: int, duration_seconds: float = None,
                  distance_meters: float = None, hr_zone: int = 1) -> ExecutableStep:
    """Paso de recuperacion entre intervalos."""
    s = create_recovery_step(duration_seconds or 120, step_order)
    if distance_meters:
        s.endCondition = {"conditionTypeId": ConditionType.DISTANCE, "conditionTypeKey": "distance"}
        s.endConditionValue = distance_meters
    t = _hr_zone_target(hr_zone)
    s.targetType = t["targetType"]
    s.targetValueOne = t.get("targetValueOne")
    s.targetValueTwo = t.get("targetValueTwo")
    return s


def steady_run(step_order: int, duration_seconds: float, hr_zone: int) -> ExecutableStep:
    """Trote continuo por tiempo en una zona de FC."""
    return ExecutableStep(
        stepOrder=step_order,
        stepType={"stepTypeId": 3, "stepTypeKey": "interval"},
        endCondition={"conditionTypeId": ConditionType.TIME, "conditionTypeKey": "time"},
        endConditionValue=duration_seconds,
        targetType=_hr_zone_target(hr_zone)["targetType"],
        targetValueOne=hr_zone,
        targetValueTwo=hr_zone,
    )


# ---------- Plantillas de workouts ----------

def build_easy_run(name: str, total_minutes: int, description: str = "") -> RunningWorkout:
    """Rodaje suave continuo en Z2. El tipo de sesion mas comun."""
    main_secs = (total_minutes - 20) * 60  # 10 min entrada + main + 10 min vuelta
    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=total_minutes * 60,
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running"},
            workoutSteps=[
                warmup(1, 600, hr_zone=2),
                steady_run(2, max(main_secs, 600), hr_zone=2),
                cooldown(3, 600, hr_zone=1),
            ]
        )]
    )


def build_tempo_run(name: str, warmup_min: int, tempo_min: int, cooldown_min: int,
                    description: str = "") -> RunningWorkout:
    """Tempo continuo en Z4 (umbral). Para desarrollar ritmo de carrera."""
    total = (warmup_min + tempo_min + cooldown_min) * 60
    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=total,
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running"},
            workoutSteps=[
                warmup(1, warmup_min * 60, hr_zone=2),
                steady_run(2, tempo_min * 60, hr_zone=4),
                cooldown(3, cooldown_min * 60, hr_zone=1),
            ]
        )]
    )


def build_interval_run(name: str, warmup_min: int, interval_distance_m: int,
                       repetitions: int, recovery_seconds: int, cooldown_min: int,
                       interval_hr_zone: int = 5, description: str = "") -> RunningWorkout:
    """Intervalos por distancia (ej: 4x1000m). Para desarrollar VO2max."""
    interval_steps = []
    for i in range(repetitions):
        interval_steps.append(interval_by_distance(i * 2 + 1, interval_distance_m, hr_zone=interval_hr_zone))
        if i < repetitions - 1:
            interval_steps.append(recovery_step(i * 2 + 2, duration_seconds=recovery_seconds))

    rep_group = create_repeat_group(1, interval_steps, step_order=2)
    estimated = (warmup_min + cooldown_min) * 60 + repetitions * (interval_distance_m / 3.5 + recovery_seconds)

    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=int(estimated),
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running"},
            workoutSteps=[
                warmup(1, warmup_min * 60, hr_zone=2),
                rep_group,
                cooldown(3, cooldown_min * 60, hr_zone=1),
            ]
        )]
    )


def build_long_run(name: str, total_minutes: int, description: str = "") -> RunningWorkout:
    """Tirada larga en Z2 con nucleo en Z3 al final para simular fatiga de carrera."""
    warmup_secs = 600
    z3_secs = min(total_minutes * 60 * 0.2, 1200)  # hasta 20 min en Z3 al final
    main_secs = total_minutes * 60 - warmup_secs - z3_secs - 600

    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=total_minutes * 60,
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running"},
            workoutSteps=[
                warmup(1, warmup_secs, hr_zone=2),
                steady_run(2, max(main_secs, 600), hr_zone=2),
                steady_run(3, int(z3_secs), hr_zone=3),
                cooldown(4, 600, hr_zone=1),
            ]
        )]
    )


def build_easy_bike(name: str, total_minutes: int, description: str = "") -> CyclingWorkout:
    """Rodaje suave de ciclismo en Z2."""
    main_secs = (total_minutes - 20) * 60
    return CyclingWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=total_minutes * 60,
        workoutSegments=[WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 2, "sportTypeKey": "cycling"},
            workoutSteps=[
                warmup(1, 600, hr_zone=2),
                steady_run(2, max(main_secs, 600), hr_zone=2),
                cooldown(3, 600, hr_zone=1),
            ]
        )]
    )


# ---------- Funciones de upload / schedule / consulta ----------

def upload_and_schedule_workout(workout_obj, date_str: str) -> dict:
    """Sube un workout a Garmin Connect y lo agenda en la fecha indicada (YYYY-MM-DD).
    Devuelve el workout_id y el scheduled_id para poder borrarlo si hace falta."""
    client = get_client()

    # 1. Subir el workout (queda guardado en "Mis Entrenamientos" de Garmin Connect)
    uploaded = client.upload_workout(workout_obj.to_dict())
    workout_id = uploaded.get("workoutId")
    if not workout_id:
        return {"error": "No se pudo obtener el workoutId tras el upload", "raw": uploaded}

    # 2. Agendarlo en la fecha indicada
    scheduled = client.schedule_workout(workout_id, date_str)
    scheduled_id = scheduled.get("scheduledWorkoutId") if isinstance(scheduled, dict) else None

    return {
        "workout_id": workout_id,
        "scheduled_id": scheduled_id,
        "name": workout_obj.workoutName,
        "date": date_str,
        "status": "agendado",
    }


def get_scheduled_workouts_for_week(date_str: str = None) -> list:
    """Devuelve los workouts ya agendados en Garmin para la semana de la fecha indicada
    (o la semana actual si no se pasa fecha)."""
    client = get_client()
    if date_str:
        d = datetime.date.fromisoformat(date_str)
    else:
        d = datetime.date.today()
    year = d.year
    month = d.month
    try:
        data = client.get_scheduled_workouts(year, month)
        return data if isinstance(data, list) else [data]
    except Exception as e:
        return [{"error": str(e)}]


def delete_scheduled_workout(scheduled_workout_id: str) -> dict:
    """Borra un workout agendado del calendario de Garmin por su scheduled_id.
    No borra el workout en sí, solo lo quita del calendario."""
    client = get_client()
    try:
        client.unschedule_workout(scheduled_workout_id)
        return {"status": "borrado", "scheduled_id": scheduled_workout_id}
    except Exception as e:
        return {"error": str(e)}
