package store

import "time"

type JobEvent struct {
	ID        int64     `json:"id"`
	JobID     string    `json:"job_id"`
	EventType string    `json:"event_type"`
	Detail    string    `json:"detail"`
	CreatedAt time.Time `json:"created_at"`
}

func (s *Store) Events(jobID string, limit int) ([]JobEvent, error) {
	if limit <= 0 || limit > 1000 { limit = 100 }
	rows, err := s.db.Query(`SELECT id,job_id,event_type,detail,created_at FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT ?`, jobID, limit)
	if err != nil { return nil, err }
	defer rows.Close()
	out := make([]JobEvent, 0)
	for rows.Next() {
		var e JobEvent
		var created string
		if err := rows.Scan(&e.ID, &e.JobID, &e.EventType, &e.Detail, &created); err != nil { return nil, err }
		e.CreatedAt, _ = time.Parse(time.RFC3339Nano, created)
		out = append(out, e)
	}
	return out, rows.Err()
}
