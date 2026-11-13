# Data dictionary

| Dataset | Primary key | Purpose |
|---|---|---|
| products | product_id | Product/SKU master and family |
| routings | routing_id | Effective-dated product routing |
| routing_operations | routing_operation_id | Ordered operation templates |
| machines | machine_id | Machine resources, type and labor group |
| eligible_machines | routing_operation_id + machine_id | N:M machine eligibility bridge |
| machine_calendars | calendar_id | Machine shift windows and labor capacity |
| machine_downtime | downtime_id | Maintenance, breakdown and quality downtime |
| materials | material_id | Material master |
| inventory_lots | lot_id | Lot quantity and availability dates |
| production_orders | order_id | Demand, due date and priority |
| operations | operation_id | Order-specific operation instances |
| material_requirements | requirement_id | Operation-to-material quantities |
| tools | tool_id | Shared tool pools and unit capacities |
| operation_tool_requirements | tool_requirement_id | Operation-to-tool bridge |
| changeover_matrix | from_family + to_family | Sequence-dependent setup minutes |
| operation_schedule | schedule_id | Generated machine/labor/tool assignments |
| scheduling_exceptions | operation_id + exception | Unscheduled operation reasons |
| event_history | event row | Traceable scheduling decisions and exceptions |
| ground_truth | scenario_id | Labels for five separate negative test scenarios |

Foreign keys are documented by column names and validated by `validate_data`.
