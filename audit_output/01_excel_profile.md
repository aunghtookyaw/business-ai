# SotePhwar Excel Profile

- Source: `/Users/bigshot/MEGA/data_audit.xlsx`
- Selected sheet: `Sheet1`
- Sheet names: `Sheet1`
- Excel data rows: 858
- Date range: 2025-01-19 to 2027-07-11
- Unique invoice numbers: 237
- Duplicate normalized headers: 0

## Exact Headers

- `Invoice_Number`
- `Item`
- `Quantity`
- `Total_Amount`
- `Amount_Received`
- `Note`
- `AI_comment`
- `Invoice_Date`
- `Customer_Name`

## Final Column Mapping

| Logical field | Excel header | Required |
|---|---|---:|
| `ai_comment` | `AI_comment` | no |
| `amount_received` | `Amount_Received` | no |
| `customer_name` | `Customer_Name` | yes |
| `invoice_date` | `Invoice_Date` | yes |
| `invoice_number` | `Invoice_Number` | yes |
| `note` | `Note` | no |
| `product` | `Item` | yes |
| `quantity` | `Quantity` | yes |
| `total_amount` | `Total_Amount` | yes |

## Blank Required Fields

- `customer_name`: 0
- `invoice_date`: 0
- `invoice_number`: 0
- `product`: 0
- `quantity`: 5
- `total_amount`: 0

## Inferred Column Types

| Exact header | Inferred type | Blank count |
|---|---|---:|
| `Invoice_Number` | mixed:integer,text | 0 |
| `Item` | text | 0 |
| `Quantity` | integer | 5 |
| `Total_Amount` | integer | 0 |
| `Amount_Received` | integer | 275 |
| `Note` | text | 360 |
| `AI_comment` | blank | 858 |
| `Invoice_Date` | datetime | 0 |
| `Customer_Name` | text | 0 |
