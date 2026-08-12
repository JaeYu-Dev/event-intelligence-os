"""
Monitor Service — Background execution loops that keep the engines running.

Three loops from the spec (P6, P7, Section 13A):
  - Strategic Loop (every 6 hours): discovery, thesis maintenance, validation
  - Cheap Monitor (every 30 seconds): anomaly detection, trigger evaluation
  - Event-Window Loop (every 1 minute): armed event rebalancing
"""
