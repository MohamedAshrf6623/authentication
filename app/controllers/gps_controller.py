from datetime import datetime, timedelta, timezone

from flask import jsonify, request

from app import db
from app.models.location import Location


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Invalid timestamp')

    raw_value = value.strip()
    if raw_value.endswith('Z'):
        raw_value = raw_value[:-1] + '+00:00'

    parsed = datetime.fromisoformat(raw_value)

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def receive_gps():
    try:
        data = request.get_json(force=True)

        coordinates = data['geometry']['coordinates']
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
            raise ValueError('Invalid coordinates format')

        longitude = float(coordinates[0])
        latitude = float(coordinates[1])

        device_id = str(data['properties']['device']).strip()
        if not device_id:
            raise ValueError('Device id is required')

        timestamp_raw = data['properties']['timestamp']
        parsed_timestamp = _parse_timestamp(timestamp_raw)

        location = Location(
            device_id=device_id,
            lat=latitude,
            lon=longitude,
            timestamp=parsed_timestamp,
        )
        db.session.add(location)

        cutoff = datetime.utcnow() - timedelta(days=7)
        Location.query.filter(Location.timestamp < cutoff).delete(synchronize_session=False)

        db.session.commit()
        return jsonify({'status': 'ok'}), 200

    except Exception as exc:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(exc)}), 400


def get_last_location():
    try:
        device_id = (request.args.get('device_id') or '').strip()
        if not device_id:
            return jsonify({'error': 'device_id is required'}), 400

        location = (
            Location.query
            .filter(Location.device_id == device_id)
            .order_by(Location.timestamp.desc())
            .first()
        )

        if not location:
            return jsonify({'error': 'not found'}), 404

        return jsonify({
            'device': device_id,
            'lat': location.lat,
            'lon': location.lon,
            'timestamp': location.timestamp.isoformat() if location.timestamp else None,
        }), 200

    except Exception as exc:
        return jsonify({'error': 'internal server error', 'message': str(exc)}), 500


def get_history():
    try:
        device_id = (request.args.get('device_id') or '').strip()
        if not device_id:
            return jsonify({'error': 'device_id is required'}), 400

        from_value = (request.args.get('from') or '').strip()
        to_value = (request.args.get('to') or '').strip()

        query = Location.query.filter(Location.device_id == device_id)

        if from_value:
            from_dt = _parse_timestamp(from_value)
            query = query.filter(Location.timestamp >= from_dt)

        if to_value:
            to_dt = _parse_timestamp(to_value)
            query = query.filter(Location.timestamp <= to_dt)

        locations = query.order_by(Location.timestamp.asc()).all()

        return jsonify([
            {
                'lat': item.lat,
                'lon': item.lon,
                'timestamp': item.timestamp.isoformat() if item.timestamp else None,
            }
            for item in locations
        ]), 200

    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': 'internal server error', 'message': str(exc)}), 500
