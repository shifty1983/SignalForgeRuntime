# Runtime Process

Daily SignalForge Runtime flow:

1. Refresh market and option data
2. Build regime state
3. Build asset behavior state
4. Build option behavior state
5. Generate decision rows
6. Generate strategy candidates
7. Apply expectancy / strategy selection
8. Select option legs
9. Apply V3.2.2 pre-trade gates
10. Apply portfolio construction and sizing
11. Generate broker paper-order rehearsal tickets
12. Capture fills and rejects
13. Reconcile paper execution against expected backtest/native quote assumptions
14. Update closed trade outcomes and prior symbol/regime state
