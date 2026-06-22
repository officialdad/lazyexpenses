#!/usr/bin/env python3
"""Build a self-contained interactive spend dashboard from transactions.csv.

Reads transactions.csv (produced by parse.py) and writes dashboard.html: a single
file with the data embedded inline and all charts hand-rolled in SVG + vanilla JS.
No external libraries, no network -> opens offline in any browser. Re-run after
parse.py to refresh.
"""
import csv, json, os, html
import insights

SRC = "transactions.csv"
OUT = "dashboard.html"

# Categories that are financing/contra, not consumption (mirror parse.py NON_SPEND).
NON_SPEND = ["Installments/BT", "Transfers/Payments", "Rebate/Cashback"]

# Stable colour per category.
COLORS = {
    "Installments/BT": "#6b7280", "Transfers/Payments": "#9ca3af",
    "Rebate/Cashback": "#34d399", "Health/Insurance": "#f472b6",
    "Travel": "#60a5fa", "Shopping": "#f59e0b", "Groceries": "#10b981",
    "F&B": "#ef4444", "Telco/Utilities": "#a78bfa", "Subscriptions": "#22d3ee",
    "Vehicle": "#0ea5e9", "Fees/Charges": "#94a3b8",
    "Entertainment": "#c084fc", "Certifications": "#818cf8", "Charity": "#2dd4bf",
    "Other": "#64748b",
}

# Category -> Material Design Icon name. Icons are inlined (see MDI below) so the
# page stays single-file and offline (no webfont/CDN). Used everywhere a category
# is named: legends, movers, the monthly table tag, recommendation chips.
CAT_ICON = {
    "Groceries": "cart", "F&B": "silverware-fork-knife", "Vehicle": "car",
    "Telco/Utilities": "flash", "Travel": "airplane", "Health/Insurance": "heart-pulse",
    "Subscriptions": "sync", "Shopping": "shopping", "Entertainment": "movie-open",
    "Certifications": "certificate", "Charity": "charity",
    "Transfers/Payments": "bank-transfer", "Fees/Charges": "cash-minus",
    "Rebate/Cashback": "cash-plus", "Installments/BT": "calendar-clock",
    "Other": "shape-outline",
}

# Verbatim MDI path data (24x24 viewBox). Keys: the CAT_ICON values above plus the
# tab/section icons used in the JS. Don't hand-edit the path strings.
MDI = {
    "cart": "M17,18C15.89,18 15,18.89 15,20A2,2 0 0,0 17,22A2,2 0 0,0 19,20C19,18.89 18.1,18 17,18M1,2V4H3L6.6,11.59L5.24,14.04C5.09,14.32 5,14.65 5,15A2,2 0 0,0 7,17H19V15H7.42A0.25,0.25 0 0,1 7.17,14.75C7.17,14.7 7.18,14.66 7.2,14.63L8.1,13H15.55C16.3,13 16.96,12.58 17.3,11.97L20.88,5.5C20.95,5.34 21,5.17 21,5A1,1 0 0,0 20,4H5.21L4.27,2M7,18C5.89,18 5,18.89 5,20A2,2 0 0,0 7,22A2,2 0 0,0 9,20C9,18.89 8.1,18 7,18Z",
    "silverware-fork-knife": "M11,9H9V2H7V9H5V2H3V9C3,11.12 4.66,12.84 6.75,12.97V22H9.25V12.97C11.34,12.84 13,11.12 13,9V2H11V9M16,6V14H18.5V22H21V2C18.24,2 16,4.24 16,6Z",
    "car": "M5,11L6.5,6.5H17.5L19,11M17.5,16A1.5,1.5 0 0,1 16,14.5A1.5,1.5 0 0,1 17.5,13A1.5,1.5 0 0,1 19,14.5A1.5,1.5 0 0,1 17.5,16M6.5,16A1.5,1.5 0 0,1 5,14.5A1.5,1.5 0 0,1 6.5,13A1.5,1.5 0 0,1 8,14.5A1.5,1.5 0 0,1 6.5,16M18.92,6C18.72,5.42 18.16,5 17.5,5H6.5C5.84,5 5.28,5.42 5.08,6L3,12V20A1,1 0 0,0 4,21H5A1,1 0 0,0 6,20V19H18V20A1,1 0 0,0 19,21H20A1,1 0 0,0 21,20V12L18.92,6Z",
    "flash": "M7,2V13H10V22L17,10H13L17,2H7Z",
    "airplane": "M20.56 3.91C21.15 4.5 21.15 5.45 20.56 6.03L16.67 9.92L18.79 19.11L17.38 20.53L13.5 13.1L9.6 17L9.96 19.47L8.89 20.53L7.13 17.35L3.94 15.58L5 14.5L7.5 14.87L11.37 11L3.94 7.09L5.36 5.68L14.55 7.8L18.44 3.91C19 3.33 20 3.33 20.56 3.91Z",
    "heart-pulse": "M7.5,4A5.5,5.5 0 0,0 2,9.5C2,10 2.09,10.5 2.22,11H6.3L7.57,7.63C7.87,6.83 9.05,6.75 9.43,7.63L11.5,13L12.09,11.58C12.22,11.25 12.57,11 13,11H21.78C21.91,10.5 22,10 22,9.5A5.5,5.5 0 0,0 16.5,4C14.64,4 13,4.93 12,6.34C11,4.93 9.36,4 7.5,4V4M3,12.5A1,1 0 0,0 2,13.5A1,1 0 0,0 3,14.5H5.44L11,20C12,20.9 12,20.9 13,20L18.56,14.5H21A1,1 0 0,0 22,13.5A1,1 0 0,0 21,12.5H13.4L12.47,14.8C12.07,15.81 10.92,15.67 10.55,14.83L8.5,9.5L7.54,11.83C7.39,12.21 7.05,12.5 6.6,12.5H3Z",
    "sync": "M12,18A6,6 0 0,1 6,12C6,11 6.25,10.03 6.7,9.2L5.24,7.74C4.46,8.97 4,10.43 4,12A8,8 0 0,0 12,20V23L16,19L12,15M12,4V1L8,5L12,9V6A6,6 0 0,1 18,12C18,13 17.75,13.97 17.3,14.8L18.76,16.26C19.54,15.03 20,13.57 20,12A8,8 0 0,0 12,4Z",
    "shopping": "M12,13A5,5 0 0,1 7,8H9A3,3 0 0,0 12,11A3,3 0 0,0 15,8H17A5,5 0 0,1 12,13M12,3A3,3 0 0,1 15,6H9A3,3 0 0,1 12,3M19,6H17A5,5 0 0,0 12,1A5,5 0 0,0 7,6H5C3.89,6 3,6.89 3,8V20A2,2 0 0,0 5,22H19A2,2 0 0,0 21,20V8C21,6.89 20.1,6 19,6Z",
    "movie-open": "M20.84 2.18L16.91 2.96L19.65 6.5L21.62 6.1L20.84 2.18M13.97 3.54L12 3.93L14.75 7.46L16.71 7.07L13.97 3.54M9.07 4.5L7.1 4.91L9.85 8.44L11.81 8.05L9.07 4.5M4.16 5.5L3.18 5.69A2 2 0 0 0 1.61 8.04L2 10L6.9 9.03L4.16 5.5M2 10V20C2 21.11 2.9 22 4 22H20C21.11 22 22 21.11 22 20V10H2Z",
    "certificate": "M4,3C2.89,3 2,3.89 2,5V15A2,2 0 0,0 4,17H12V22L15,19L18,22V17H20A2,2 0 0,0 22,15V8L22,6V5A2,2 0 0,0 20,3H16V3H4M12,5L15,7L18,5V8.5L21,10L18,11.5V15L15,13L12,15V11.5L9,10L12,8.5V5M4,5H9V7H4V5M4,9H7V11H4V9M4,13H9V15H4V13Z",
    "charity": "M12.75,3.94C13.75,3.22 14.91,2.86 16.22,2.86C16.94,2.86 17.73,3.05 18.59,3.45C19.45,3.84 20.13,4.3 20.63,4.83C21.66,6.11 22.09,7.6 21.94,9.3C21.78,11 21.22,12.33 20.25,13.27L12.66,20.86C12.47,21.05 12.23,21.14 11.95,21.14C11.67,21.14 11.44,21.05 11.25,20.86C11.06,20.67 10.97,20.44 10.97,20.16C10.97,19.88 11.06,19.64 11.25,19.45L15.84,14.86C16.09,14.64 16.09,14.41 15.84,14.16C15.59,13.91 15.36,13.91 15.14,14.16L10.55,18.75C10.36,18.94 10.13,19.03 9.84,19.03C9.56,19.03 9.33,18.94 9.14,18.75C8.95,18.56 8.86,18.33 8.86,18.05C8.86,17.77 8.95,17.53 9.14,17.34L13.73,12.75C14,12.5 14,12.25 13.73,12C13.5,11.75 13.28,11.75 13.03,12L8.44,16.64C8.25,16.83 8,16.92 7.73,16.92C7.45,16.92 7.21,16.83 7,16.64C6.8,16.45 6.7,16.22 6.7,15.94C6.7,15.66 6.81,15.41 7.03,15.19L11.63,10.59C11.88,10.34 11.88,10.11 11.63,9.89C11.38,9.67 11.14,9.67 10.92,9.89L6.28,14.5C6.06,14.7 5.83,14.81 5.58,14.81C5.3,14.81 5.06,14.71 4.88,14.5C4.69,14.3 4.59,14.06 4.59,13.78C4.59,13.5 4.69,13.27 4.88,13.08C7.94,10 9.83,8.14 10.55,7.45L14.11,10.97C14.5,11.34 14.95,11.53 15.5,11.53C16.2,11.53 16.75,11.25 17.16,10.69C17.44,10.28 17.54,9.83 17.46,9.33C17.38,8.83 17.17,8.41 16.83,8.06L12.75,3.94M14.81,10.27L10.55,6L3.47,13.08C2.63,12.23 2.15,10.93 2.04,9.16C1.93,7.4 2.41,5.87 3.47,4.59C4.66,3.41 6.08,2.81 7.73,2.81C9.39,2.81 10.8,3.41 11.95,4.59L16.22,8.86C16.41,9.05 16.5,9.28 16.5,9.56C16.5,9.84 16.41,10.08 16.22,10.27C16.03,10.45 15.8,10.55 15.5,10.55C15.23,10.55 15,10.45 14.81,10.27V10.27Z",
    "bank-transfer": "M15,14V11H18V9L22,12.5L18,16V14H15M14,7.7V9H2V7.7L8,4L14,7.7M7,10H9V15H7V10M3,10H5V15H3V10M13,10V12.5L11,14.3V10H13M9.1,16L8.5,16.5L10.2,18H2V16H9.1M17,15V18H14V20L10,16.5L14,13V15H17Z",
    "cash-minus": "M15 15V17H23V15M14.97 11.61C14.85 10.28 13.59 8.97 12 9C10.3 9.03 9 10.3 9 12C9 13.7 10.3 14.94 12 15C12.38 15 12.77 14.92 13.14 14.77C13.41 13.67 13.86 12.63 14.97 11.61M13 16H7C7 14.9 6.11 14 5 14V10C6.11 10 7 9.11 7 8H17C17 9.11 17.9 10 19 10V10.06C19.67 10.06 20.34 10.18 21 10.4V6H3V18H13.32C13.1 17.33 13 16.66 13 16Z",
    "cash-plus": "M15 15V17H18V20H20V17H23V15H20V12H18V15M14.97 11.61C14.85 10.28 13.59 8.97 12 9C10.3 9.03 9 10.3 9 12C9 13.7 10.3 14.94 12 15C12.38 15 12.77 14.92 13.14 14.77C13.41 13.67 13.86 12.63 14.97 11.61M13 16H7C7 14.9 6.11 14 5 14V10C6.11 10 7 9.11 7 8H17C17 9.11 17.9 10 19 10V10.06C19.67 10.06 20.34 10.18 21 10.4V6H3V18H13.32C13.1 17.33 13 16.66 13 16Z",
    "calendar-clock": "M15,13H16.5V15.82L18.94,17.23L18.19,18.53L15,16.69V13M19,8H5V19H9.67C9.24,18.09 9,17.07 9,16A7,7 0 0,1 16,9C17.07,9 18.09,9.24 19,9.67V8M5,21C3.89,21 3,20.1 3,19V5C3,3.89 3.89,3 5,3H6V1H8V3H16V1H18V3H19A2,2 0 0,1 21,5V11.1C22.24,12.36 23,14.09 23,16A7,7 0 0,1 16,23C14.09,23 12.36,22.24 11.1,21H5M16,11.15A4.85,4.85 0 0,0 11.15,16C11.15,18.68 13.32,20.85 16,20.85A4.85,4.85 0 0,0 20.85,16C20.85,13.32 18.68,11.15 16,11.15Z",
    "shape-outline": "M11,13.5V21.5H3V13.5H11M9,15.5H5V19.5H9V15.5M12,2L17.5,11H6.5L12,2M12,5.86L10.08,9H13.92L12,5.86M17.5,13C20,13 22,15 22,17.5C22,20 20,22 17.5,22C15,22 13,20 13,17.5C13,15 15,13 17.5,13M17.5,15A2.5,2.5 0 0,0 15,17.5A2.5,2.5 0 0,0 17.5,20A2.5,2.5 0 0,0 20,17.5A2.5,2.5 0 0,0 17.5,15Z",
    "calendar-month": "M9,10V12H7V10H9M13,10V12H11V10H13M17,10V12H15V10H17M19,3A2,2 0 0,1 21,5V19A2,2 0 0,1 19,21H5C3.89,21 3,20.1 3,19V5A2,2 0 0,1 5,3H6V1H8V3H16V1H18V3H19M19,19V8H5V19H19M9,14V16H7V14H9M13,14V16H11V14H13M17,14V16H15V14H17Z",
    "view-dashboard": "M13,3V9H21V3M13,21H21V11H13M3,21H11V15H3M3,13H11V3H3V13Z",
    "content-cut": "M19,3L13,9L15,11L22,4V3M12,12.5A0.5,0.5 0 0,1 11.5,12A0.5,0.5 0 0,1 12,11.5A0.5,0.5 0 0,1 12.5,12A0.5,0.5 0 0,1 12,12.5M6,20A2,2 0 0,1 4,18C4,16.89 4.9,16 6,16A2,2 0 0,1 8,18C8,19.11 7.1,20 6,20M6,8A2,2 0 0,1 4,6C4,4.89 4.9,4 6,4A2,2 0 0,1 8,6C8,7.11 7.1,8 6,8M9.64,7.64C9.87,7.14 10,6.59 10,6A4,4 0 0,0 6,2A4,4 0 0,0 2,6A4,4 0 0,0 6,10C6.59,10 7.14,9.87 7.64,9.64L10,12L7.64,14.36C7.14,14.13 6.59,14 6,14A4,4 0 0,0 2,18A4,4 0 0,0 6,22A4,4 0 0,0 10,18C10,17.41 9.87,16.86 9.64,16.36L12,14L19,21H22V20L9.64,7.64Z",
    "trending-up": "M16,6L18.29,8.29L13.41,13.17L9.41,9.17L2,16.59L3.41,18L9.41,12L13.41,16L19.71,9.71L22,12V6H16Z",
    "alert-circle": "M13,13H11V7H13M13,17H11V15H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z",
    "chart-line": "M16,11.78L20.24,4.45L21.97,5.45L16.74,14.5L10.23,10.75L5.46,19H22V21H2V3H4V17.54L9.5,8L16,11.78Z",
    "chart-donut": "M13,2.05V5.08C16.39,5.57 19,8.47 19,12C19,12.9 18.82,13.75 18.5,14.54L21.12,16.07C21.68,14.83 22,13.45 22,12C22,6.82 18.05,2.55 13,2.05M12,19A7,7 0 0,1 5,12C5,8.47 7.61,5.57 11,5.08V2.05C5.94,2.55 2,6.81 2,12A10,10 0 0,0 12,22C15.3,22 18.23,20.39 20.05,17.91L17.45,16.38C16.17,18 14.21,19 12,19Z",
    "credit-card-outline": "M20,8H4V6H20M20,18H4V12H20M20,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V6C22,4.89 21.1,4 20,4Z",
    "view-grid-outline": "M3 11H11V3H3M5 5H9V9H5M13 21H21V13H13M15 15H19V19H15M3 21H11V13H3M5 15H9V19H5M13 3V11H21V3M19 9H15V5H19Z",
    "storefront-outline": "M5.06 3C4.63 3 4.22 3.14 3.84 3.42S3.24 4.06 3.14 4.5L2.11 8.91C1.86 10 2.06 10.95 2.72 11.77L3 12.05V19C3 19.5 3.2 20 3.61 20.39S4.5 21 5 21H19C19.5 21 20 20.8 20.39 20.39S21 19.5 21 19V12.05L21.28 11.77C21.94 10.95 22.14 10 21.89 8.91L20.86 4.5C20.73 4.06 20.5 3.7 20.13 3.42C19.77 3.14 19.38 3 18.94 3H5.06M18.89 4.97L19.97 9.38C20.06 9.81 19.97 10.2 19.69 10.55C19.44 10.86 19.13 11 18.75 11C18.44 11 18.17 10.9 17.95 10.66C17.73 10.43 17.61 10.16 17.58 9.84L16.97 5L18.89 4.97M5.06 5H7.03L6.42 9.84C6.3 10.63 5.91 11 5.25 11C4.84 11 4.53 10.86 4.31 10.55C4.03 10.2 3.94 9.81 4.03 9.38L5.06 5M9.05 5H11V9.7C11 10.05 10.89 10.35 10.64 10.62C10.39 10.88 10.08 11 9.7 11C9.36 11 9.07 10.88 8.84 10.59S8.5 10 8.5 9.66V9.5L9.05 5M13 5H14.95L15.5 9.5C15.58 9.92 15.5 10.27 15.21 10.57C14.95 10.87 14.61 11 14.2 11C13.89 11 13.61 10.88 13.36 10.62C13.11 10.35 13 10.05 13 9.7V5M7.45 12.05C8.08 12.67 8.86 13 9.8 13C10.64 13 11.38 12.67 12 12.05C12.69 12.67 13.45 13 14.3 13C15.17 13 15.92 12.67 16.55 12.05C17.11 12.67 17.86 13 18.8 13H19.03V19H5V13H5.25C6.16 13 6.89 12.67 7.45 12.05Z",
    "swap-vertical": "M9,3L5,7H8V14H10V7H13M16,17V10H14V17H11L15,21L19,17H16Z",
    "table": "M5,4H19A2,2 0 0,1 21,6V18A2,2 0 0,1 19,20H5A2,2 0 0,1 3,18V6A2,2 0 0,1 5,4M5,8V12H11V8H5M13,8V12H19V8H13M5,14V18H11V14H5M13,14V18H19V14H13Z",
    "receipt-text-outline": "M19.5 3.5L18 2L16.5 3.5L15 2L13.5 3.5L12 2L10.5 3.5L9 2L7.5 3.5L6 2L4.5 3.5L3 2V22L4.5 20.5L6 22L7.5 20.5L9 22L10.5 20.5L12 22L13.5 20.5L15 22L16.5 20.5L18 22L19.5 20.5L21 22V2L19.5 3.5M19 19H5V5H19V19M6 15H18V17H6M6 11H18V13H6M6 7H18V9H6V7Z",
    "counter": "M4,4H20A2,2 0 0,1 22,6V18A2,2 0 0,1 20,20H4A2,2 0 0,1 2,18V6A2,2 0 0,1 4,4M4,6V18H11V6H4M20,18V6H18.76C19,6.54 18.95,7.07 18.95,7.13C18.88,7.8 18.41,8.5 18.24,8.75L15.91,11.3L19.23,11.28L19.24,12.5L14.04,12.47L14,11.47C14,11.47 17.05,8.24 17.2,7.95C17.34,7.67 17.91,6 16.5,6C15.27,6.05 15.41,7.3 15.41,7.3L13.87,7.31C13.87,7.31 13.88,6.65 14.25,6H13V18H15.58L15.57,17.14L16.54,17.13C16.54,17.13 17.45,16.97 17.46,16.08C17.5,15.08 16.65,15.08 16.5,15.08C16.37,15.08 15.43,15.13 15.43,15.95H13.91C13.91,15.95 13.95,13.89 16.5,13.89C19.1,13.89 18.96,15.91 18.96,15.91C18.96,15.91 19,17.16 17.85,17.63L18.37,18H20M8.92,16H7.42V10.2L5.62,10.76V9.53L8.76,8.41H8.92V16Z",
    "piggy-bank-outline": "M15 10C15 9.45 15.45 9 16 9C16.55 9 17 9.45 17 10S16.55 11 16 11 15 10.55 15 10M8 9H13V7H8V9M22 7.5V14.47L19.18 15.41L17.5 21H12V19H10V21H4.5C4.5 21 2 12.54 2 9.5S4.46 4 7.5 4H12.5C13.41 2.79 14.86 2 16.5 2C17.33 2 18 2.67 18 3.5C18 3.71 17.96 3.9 17.88 4.08C17.74 4.42 17.62 4.81 17.56 5.23L19.83 7.5H22M20 9.5H19L15.5 6C15.5 5.35 15.59 4.71 15.76 4.09C14.79 4.34 14 5.06 13.67 6H7.5C5.57 6 4 7.57 4 9.5C4 11.38 5.22 16.15 6 19H8V17H14V19H16L17.56 13.85L20 13.03V9.5Z",
    "wallet-outline": "M5,3C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V16.72C21.59,16.37 22,15.74 22,15V9C22,8.26 21.59,7.63 21,7.28V5A2,2 0 0,0 19,3H5M5,5H19V7H13A2,2 0 0,0 11,9V15A2,2 0 0,0 13,17H19V19H5V5M13,9H20V15H13V9M16,10.5A1.5,1.5 0 0,0 14.5,12A1.5,1.5 0 0,0 16,13.5A1.5,1.5 0 0,0 17.5,12A1.5,1.5 0 0,0 16,10.5Z",
    "cash-multiple": "M5,6H23V18H5V6M14,9A3,3 0 0,1 17,12A3,3 0 0,1 14,15A3,3 0 0,1 11,12A3,3 0 0,1 14,9M9,8A2,2 0 0,1 7,10V14A2,2 0 0,1 9,16H19A2,2 0 0,1 21,14V10A2,2 0 0,1 19,8H9M1,10H3V20H19V22H1V10Z",
    "filter-variant": "M6,13H18V11H6M3,6V8H21V6M10,18H14V16H10V18Z",
}


def load():
    rows = []
    with open(SRC, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "c": f"{r['bank']}·{r['card_last4']}",
                "m": r["statement_month"],
                "g": r["category"],
                "a": round(float(r["amount"]), 2),
                "t": 0 if r["type"] == "debit" else 1,
                "d": r["description"][:46],
            })
    return rows


def build():
    rows = load()
    months = sorted({r["m"] for r in rows})
    cards = sorted({r["c"] for r in rows})
    cats = [c for c in COLORS if any(r["g"] == c for r in rows)]
    recs = insights.compute(rows)
    payload = {
        "rows": rows, "months": months, "cards": cards, "cats": cats,
        "nonSpend": NON_SPEND, "colors": COLORS,
        "catIcon": CAT_ICON, "icons": MDI,
        "range": f"{months[0]} → {months[-1]}" if months else "",
        "recs": recs,
    }
    tpl = PAGE.replace("/*DATA*/", json.dumps(payload, separators=(",", ":")))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(tpl)
    print(f"wrote {OUT}: {len(rows)} txns, {len(cards)} cards, {len(months)} months, {len(cats)} categories")


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Credit-Card Spend Dashboard</title>
<style>
:root{--bg:#0f1216;--panel:#171c23;--panel2:#1d242d;--line:#2a323d;--ink:#e6edf3;--mut:#8b97a6;--accent:#60a5fa;--red:#f87171;--green:#34d399;--mono:ui-monospace,"SF Mono","Cascadia Mono","JetBrains Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}
/* inline MDI icons: fixed em-box, inherit text colour. Overrides the full-width svg{} rule below. */
.mdi{display:inline-block;width:1.05em;height:1.05em;fill:currentColor;vertical-align:-.16em;flex:none}
.tabi{margin-right:6px;vertical-align:-.18em}
.h2ic{margin-right:7px;color:var(--mut);flex:none}
.kpi .lab .mdi{margin-right:5px;vertical-align:-.15em;opacity:.8}
.lab .mdi{vertical-align:-.15em}
/* monospace tabular figures wherever money/counts are shown — column-aligned, ledger feel. */
.kpi .val,.hero .big,.hero .cb .amt,.hero .delta,.delta,.badge,.mvhead .d,td.num,th.num,.dtbl td.num,.dtbl th.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.kpi .val small,.hero .delta,.badge .ln{font-family:var(--mono)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
svg [tabindex]:focus-visible{outline:2px solid #fff;outline-offset:1px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:20px}
h1{font-size:20px;margin:0 0 2px}
.sub{color:var(--mut);font-size:12px;margin-bottom:16px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{background:var(--panel);color:var(--mut);border:0;padding:7px 14px;cursor:pointer;font:inherit}
.seg button.on{background:var(--accent);color:#06121f;font-weight:600}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--mut);border-radius:999px;padding:5px 12px;cursor:pointer;font:inherit;display:inline-flex;align-items:center;gap:6px}
.chip.on{color:var(--ink);border-color:#3a4452;background:var(--panel2)}
.chip .dot{width:9px;height:9px;border-radius:50%}
.spacer{flex:1}
.btn{border:1px solid var(--line);background:var(--panel);color:var(--mut);border-radius:8px;padding:6px 11px;cursor:pointer;font:inherit}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:6px 0 18px}
#mkpis{grid-template-columns:repeat(3,1fr)}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 15px}
.kpi .lab{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.kpi .val{font-size:21px;font-weight:700;margin-top:5px}
.kpi .val small{font-size:12px;color:var(--mut);font-weight:500}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid>*{min-width:0}/* let grid items shrink below content min-width (table/svg) so cards never force horizontal scroll on mobile */
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card.full{grid-column:1/-1}
.card h2{font-size:13px;margin:0 0 10px;color:var(--ink);font-weight:600;display:flex;align-items:center}
.card h2 span{color:var(--mut);font-weight:400;margin-left:auto;padding-left:10px;text-align:right}
svg{display:block;width:100%;overflow:visible}
.tt{position:fixed;pointer-events:none;background:#0b0e12;border:1px solid var(--line);border-radius:7px;padding:6px 9px;font-size:12px;color:var(--ink);opacity:0;transition:opacity .08s;z-index:9;white-space:nowrap;box-shadow:0 6px 20px #0008}
.lg{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:8px}
.lg span{display:inline-flex;align-items:center;gap:5px;color:var(--mut);font-size:11px}
.lg i{width:9px;height:9px;border-radius:2px;display:inline-block}
text{fill:var(--mut);font:11px system-ui}
.axis{stroke:var(--line)}
.view{display:none}.view.on{display:block}
.mnav{display:flex;align-items:center;gap:8px}
.mnav select{background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 12px;font:inherit;min-width:160px}
.delta{font-size:12px;font-weight:500;margin-top:3px}
.up{color:var(--red)}.down{color:var(--green)}
.hero{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:6px 0 14px;display:grid;grid-template-columns:1.3fr 1fr;gap:18px}
.hero .head .lab{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.hero .head .big{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums;margin-top:2px}
.hero .head .delta{font-size:13px;margin-top:4px}
.hero .cb{align-self:center;justify-self:end;text-align:right}
.hero .cb .lab{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.hero .cb .amt{color:#34d399;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:3px}
@media(max-width:860px){.hero{grid-template-columns:1fr}.hero .cb{justify-self:start;text-align:left}}
.hero .movers{grid-column:1/-1;border-top:1px solid var(--line);padding-top:12px;margin-top:2px}
.hero .movers .lab{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px}
.mvrow{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:9px;padding:8px 11px;margin-bottom:7px;cursor:pointer}
.mvrow:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.mvhead{display:flex;justify-content:space-between;align-items:center;gap:10px}
.mvhead .nm{display:flex;align-items:center;gap:7px}
.mvhead .nm i{width:9px;height:9px;border-radius:2px;display:inline-block}
.mvhead .d{font-variant-numeric:tabular-nums;font-weight:700}
.mvrow .detail{display:none;margin-top:8px;border-top:1px solid var(--line);padding-top:7px}
.mvrow.open .detail{display:block}
.hero .cuts{grid-column:1/-1;border-top:1px solid var(--line);padding-top:12px;margin-top:2px}
.hero .cuts .lab{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px}
.cutrow{display:flex;justify-content:space-between;align-items:center;gap:10px;border:1px solid var(--line);border-radius:9px;padding:8px 11px;margin-bottom:7px;cursor:pointer}
.cutrow:hover{background:var(--panel2)}
.cutrow:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cutrow .ttl{font-weight:600}
.cutrow .ln{color:var(--mut);font-size:12px}
.cutrow .badge{font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap;text-align:right}
.cutrow .arrow{color:var(--mut);margin-left:6px}
.tblwrap{max-height:440px;overflow:auto;border:1px solid var(--line);border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:7px 11px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600;cursor:pointer;user-select:none;position:sticky;top:0;background:var(--panel);z-index:1}
th:hover{color:var(--ink)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr:hover td{background:var(--panel2)}
.tag{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px}
.cr{color:#34d399}
@media(max-width:860px){.grid{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}}
@media(max-width:560px){.wrap{padding:12px}.kpis,#mkpis{grid-template-columns:1fr 1fr}.hero{padding:13px 14px;gap:12px}.hero .head .big{font-size:25px}.hero .cb .amt{font-size:19px}.cutrow{flex-wrap:wrap}table{font-size:12px}th,td{padding:6px 8px}}
.rec{grid-column:1/-1;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 15px;display:flex;flex-direction:column;cursor:pointer}
.rec:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.rechead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.rec .ttl{font-weight:600;margin-bottom:3px}
.rec .ln{color:var(--mut);font-size:12px}
.rec .badge{font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap;text-align:right}
.rec .hint{display:inline-block;margin-top:6px;font-size:11px;border:1px solid var(--line);border-radius:999px;padding:2px 9px;color:var(--mut)}
.rec .car{display:inline-block;transition:transform .15s;color:var(--mut)}
.rec.open .car{transform:rotate(90deg)}
.rec .detail{display:none;margin-top:10px;border-top:1px solid var(--line);padding-top:9px}
.rec.open .detail{display:block}
.rec.stale{opacity:.72}
.stalebadge{display:inline-block;margin-left:8px;font-size:11px;color:#fbbf24;border:1px solid #fbbf2455;border-radius:999px;padding:1px 8px;vertical-align:middle}
.dtbl{width:100%;border-collapse:collapse;font-size:12px}
.dtbl td,.dtbl th{padding:4px 8px;border-bottom:1px solid var(--line);text-align:left;color:var(--mut)}
.dtbl th{font-weight:600}
.dtbl td.num,.dtbl th.num{text-align:right;font-variant-numeric:tabular-nums}
.dtbl tr.last td{color:var(--ink);font-weight:600}
.recsec{grid-column:1/-1;margin:6px 0 2px;color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.seci{margin-right:7px;vertical-align:-.16em;opacity:.85}
.tag .mdi,.catchip .mdi{vertical-align:-.15em}
.rectype-sub .badge{color:#f59e0b}.rectype-creep .badge{color:#ef4444}.rectype-oneoff .badge{color:#60a5fa}
.rectype-installment .badge{color:#9ca3af}
.rectype-transfer .badge{color:#fb923c}
.catchip{display:inline-block;margin-left:8px;font-size:11px;border-radius:999px;padding:1px 8px;vertical-align:middle}
</style></head>
<body><div class="wrap">
<h1>Credit-Card Spend Dashboard</h1>
<div class="sub" id="rangelab"></div>

<div class="bar">
  <div class="seg" id="view">
    <button data-v="monthly" class="on">This Month</button>
    <button data-v="overview">Overview</button>
    <button data-v="recs">Recommendations</button>
  </div>
  <div class="seg" id="mode">
    <button data-m="disc" class="on">Discretionary</button>
    <button data-m="all">All (incl. financing)</button>
  </div>
  <span class="spacer"></span>
  <button class="btn" id="reset">Reset filters</button>
</div>

<div class="bar" id="cardchips"></div>

<div class="view" id="view-overview">
  <div class="kpis" id="kpis"></div>
  <div class="grid">
    <div class="card full"><h2 data-ic="chart-line">Monthly spend by category <span id="t-trend"></span></h2><svg id="trend"></svg><div class="lg" id="trendlg"></div></div>
    <div class="card"><h2 data-ic="credit-card-outline">Spend by card <span>click to filter</span></h2><svg id="bycard"></svg></div>
    <div class="card"><h2 data-ic="chart-donut">Category share <span id="t-donut"></span></h2><svg id="donut"></svg></div>
    <div class="card full"><h2 data-ic="view-grid-outline">Card × category heatmap <span>RM, darker = more</span></h2><svg id="heat"></svg></div>
    <div class="card full"><h2 data-ic="storefront-outline">Top merchants <span>top 20 by spend</span></h2><svg id="merch"></svg></div>
    <div class="card"><h2 data-ic="cash-multiple">Cashback &amp; rebates by card <span id="t-cbcard"></span></h2><svg id="cbcard"></svg></div>
    <div class="card"><h2 data-ic="cash-multiple">Cashback &amp; rebates by month <span>credited back</span></h2><svg id="cbmonth"></svg></div>
  </div>
  <div class="sub" style="margin-top:14px">Discretionary view drops Installments/BT, Transfers/Payments &amp; Rebate/Cashback (financing/contra, not consumption). Cashback/rebates are credits (money in) so they never count as spend — the two green panels above present them on their own. The Discretionary/All toggle does not affect them.</div>
</div>

<div class="view on" id="view-monthly">
  <div class="bar mnav">
    <button class="btn" id="mprev">‹ Prev</button>
    <select id="monthsel"></select>
    <button class="btn" id="mnext">Next ›</button>
    <span class="spacer"></span>
  </div>
  <div class="hero" id="hero"></div>
  <div class="kpis" id="mkpis"></div>
  <div class="grid">
    <div class="card"><h2 data-ic="credit-card-outline">Spend by card <span>click to filter</span></h2><svg id="mcard"></svg></div>
    <div class="card"><h2 data-ic="chart-donut">Category share <span id="t-mdonut"></span></h2><svg id="mdonut"></svg></div>
    <div class="card full"><h2 data-ic="swap-vertical">Change vs previous month <span>Δ RM by category · red = more, green = less</span></h2><svg id="mom"></svg></div>
    <div class="card full"><h2 data-ic="table">Transactions <span id="t-mtbl"></span></h2><div class="tblwrap"><table id="mtbl"></table></div></div>
  </div>
  <div class="sub" style="margin-top:14px">Table lists every transaction in the month (debits + credits) for the selected cards; click a column header to sort. KPIs &amp; charts follow the Discretionary/All toggle.</div>
</div>

<div class="view" id="view-recs">
  <div class="kpis" id="reckpis"></div>
  <div class="grid" id="recgrid"></div>
  <div class="sub" style="margin-top:14px">Leaks detected deterministically from your statements: recurring subscriptions, categories creeping up over the last 3 months vs the prior 3, and unusually large one-off charges. Ranked by yearly RM impact. Read-only — act in your bank app. Respects the card filter above.</div>
</div>
</div>

<div class="tt" id="tt" aria-hidden="true"></div>
<script>
const D=/*DATA*/;
const C=D.colors, NS=new Set(D.nonSpend);
// inline MDI icon (decorative — labels sit next to it, so aria-hidden). cls optional.
function svgIcon(n,cls){const p=D.icons&&D.icons[n];return p?`<svg class="mdi${cls?' '+cls:''}" viewBox="0 0 24 24" aria-hidden="true"><path d="${p}"/></svg>`:"";}
// category icon, tinted to the category colour.
function catIcon(g){const ic=svgIcon((D.catIcon&&D.catIcon[g])||"shape-outline");return ic?`<span style="color:${C[g]||'#64748b'}">${ic}</span>`:"";}
const fmt=n=>"RM"+n.toLocaleString("en-MY",{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtk=n=>n>=1000?"RM"+(n/1000).toFixed(1)+"k":"RM"+n.toFixed(0);
const SVGNS="http://www.w3.org/2000/svg";
const el=(t,a={})=>{const e=document.createElementNS(SVGNS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const tt=document.getElementById("tt");
function show(ev,h){tt.innerHTML=h;tt.style.opacity=1;tt.style.left=(ev.clientX+12)+"px";tt.style.top=(ev.clientY+12)+"px";}
function hide(){tt.style.opacity=0;}
// plain-text form of a tooltip's HTML, reused as the element's aria-label.
function plain(h){return String(h).replace(/<br\s*\/?>/gi," · ").replace(/<[^>]+>/g,"").replace(/\s+/g," ").trim();}
// position the tooltip from an element's box (for keyboard focus / touch, which carry no pointer coords).
function showAt(node,h){tt.innerHTML=h;tt.style.opacity=1;
  const r=node.getBoundingClientRect&&node.getBoundingClientRect();
  if(r){tt.style.left=(r.left+r.width/2)+"px";tt.style.top=(r.bottom+8)+"px";}}
// Make an SVG element accessible: a focusable, labelled tooltip target reachable by mouse, keyboard and touch.
// Pass onClick to turn it into a keyboard-activatable button (Enter/Space) instead of a static image.
function tip(node,h,onClick){
  node.setAttribute("tabindex","0");node.setAttribute("aria-label",plain(h));
  if(onClick){node.setAttribute("role","button");node.style.cursor="pointer";
    node.addEventListener("click",onClick);
    node.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();onClick(e);}});
  }else node.setAttribute("role","img");
  node.addEventListener("mousemove",e=>show(e,h));
  node.addEventListener("mouseleave",hide);
  node.addEventListener("focus",()=>showAt(node,h));
  node.addEventListener("blur",hide);
  node.addEventListener("touchstart",e=>{if(e.stopPropagation)e.stopPropagation();showAt(node,h);},{passive:true});
}
if(document.addEventListener)document.addEventListener("touchstart",hide,{passive:true});

let mode="disc";
let view="monthly";
let curMonth=D.months.length?D.months[D.months.length-1]:"";
const selCards=new Set(D.cards);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

document.getElementById("rangelab").textContent=D.range+"  ·  "+D.cards.length+" cards  ·  "+D.months.length+" months";

// ---- card chips ----
const cc=document.getElementById("cardchips");
D.cards.forEach(c=>{
  const b=document.createElement("button");b.className="chip on";b.dataset.c=c;
  b.innerHTML=`<i class="dot" style="background:${pickCardColor(c)}"></i>${c}`;
  b.onclick=()=>{selCards.has(c)?selCards.delete(c):selCards.add(c);if(!selCards.size)selCards.add(c);syncChips();render();};
  cc.appendChild(b);
});
function pickCardColor(c){const p=["#60a5fa","#f59e0b","#10b981","#ef4444","#a78bfa","#22d3ee","#f472b6"];return p[D.cards.indexOf(c)%p.length];}
function syncChips(){[...cc.children].forEach(b=>b.classList.toggle("on",selCards.has(b.dataset.c)));}

const recgridEl=document.getElementById("recgrid");
function toggleRec(t){const c=t.closest(".rec");if(!c)return;const open=c.classList.toggle("open");c.setAttribute("aria-expanded",open?"true":"false");}
recgridEl.addEventListener("click",e=>toggleRec(e.target));
recgridEl.addEventListener("keydown",e=>{if((e.key==="Enter"||e.key===" ")&&e.target.classList&&e.target.classList.contains("rec")){e.preventDefault();toggleRec(e.target);}});

const heroEl=document.getElementById("hero");
function toggleMv(t){const c=t.closest?t.closest(".mvrow"):null;if(!c)return;const open=c.classList.toggle("open");c.setAttribute("aria-expanded",open?"true":"false");}
heroEl.addEventListener("click",e=>{const cut=e.target.closest?e.target.closest(".cutrow"):null;if(cut){gotoRecs();return;}toggleMv(e.target);});
heroEl.addEventListener("keydown",e=>{if(e.key!=="Enter"&&e.key!==" ")return;const cls=e.target.classList;if(cls&&cls.contains("cutrow")){e.preventDefault();gotoRecs();return;}if(cls&&cls.contains("mvrow")){e.preventDefault();toggleMv(e.target);}});

document.querySelectorAll("#mode button").forEach(b=>b.onclick=()=>{
  mode=b.dataset.m;document.querySelectorAll("#mode button").forEach(x=>x.classList.toggle("on",x===b));render();});
document.getElementById("reset").onclick=()=>{D.cards.forEach(c=>selCards.add(c));mode="disc";
  document.querySelectorAll("#mode button").forEach(x=>x.classList.toggle("on",x.dataset.m==="disc"));syncChips();render();};

document.querySelectorAll("#view button").forEach(b=>b.onclick=()=>{
  view=b.dataset.v;document.querySelectorAll("#view button").forEach(x=>x.classList.toggle("on",x===b));
  document.getElementById("view-overview").classList.toggle("on",view==="overview");
  document.getElementById("view-monthly").classList.toggle("on",view==="monthly");
  document.getElementById("view-recs").classList.toggle("on",view==="recs");render();});
// prepend an icon to each tab (keeps dataset.v intact for the handlers above).
{const TABI={monthly:"calendar-month",overview:"view-dashboard",recs:"content-cut"};
 document.querySelectorAll("#view button").forEach(b=>{b.innerHTML=svgIcon(TABI[b.dataset.v],"tabi")+`<span>${b.textContent}</span>`;});}
// prepend the data-ic icon to each chart heading (runs before first render; t-* sub-spans keep their ids).
document.querySelectorAll(".card h2[data-ic]").forEach(h=>h.insertAdjacentHTML("afterbegin",svgIcon(h.dataset.ic,"h2ic")));
{const r=document.getElementById("reset");r.innerHTML=svgIcon("filter-variant","tabi")+`<span>${r.textContent}</span>`;}
document.getElementById("mprev").onclick=()=>{const i=D.months.indexOf(curMonth);if(i>0){curMonth=D.months[i-1];renderMonthly();}};
document.getElementById("mnext").onclick=()=>{const i=D.months.indexOf(curMonth);if(i<D.months.length-1){curMonth=D.months[i+1];renderMonthly();}};

// ---- filtering ----
// Signed contribution to "spend": consumption categories net refunds (debit +amount, credit -amount,
// e.g. a cancelled booking); financing categories are debit-only/gross (their credits are bill
// payments & cashback, which are not negative spend). Mirrors parse.py's summary logic.
function val(r){return NS.has(r.g)?(r.t?0:r.a):(r.t?-r.a:r.a);}
function spendRows(){return D.rows.filter(r=>selCards.has(r.c)&&(mode==="all"||!NS.has(r.g))&&!(NS.has(r.g)&&r.t===1));}
function activeCats(){return D.cats.filter(g=>mode==="all"||!NS.has(g));}

function render(){ if(view==="overview")renderOverview(); else if(view==="monthly")renderMonthly(); else renderRecs(); }
function renderOverview(){
  const rows=spendRows();
  kpis(rows,"kpis");trend(rows);byCard(rows,"bycard");donut(rows,"donut","t-donut");heat(rows);merch(rows);
  cashbackCard();cashbackMonth();
}

// Cashback/rebates are credits (type=1) in the Rebate/Cashback category -> money earned back,
// never part of spend. Presented on their own, unaffected by the Discretionary/All toggle.
function cbRows(){return D.rows.filter(r=>selCards.has(r.c)&&r.t===1&&r.g==="Rebate/Cashback");}
function cashbackCard(){
  const rows=cbRows(),by={};rows.forEach(r=>by[r.c]=(by[r.c]||0)+r.a);
  const data=Object.entries(by).sort((a,b)=>b[1]-a[1]);
  hbar("cbcard",data.length?data:[["— none —",0]],()=>"#34d399",false);
  document.getElementById("t-cbcard").textContent=fmt(rows.reduce((s,r)=>s+r.a,0))+" total";
}
function cashbackMonth(){
  const rows=cbRows(),bm={};D.months.forEach(m=>bm[m]=0);rows.forEach(r=>bm[r.m]+=r.a);
  hbar("cbmonth",D.months.map(m=>[m.slice(2),bm[m]]),()=>"#34d399",false);
}

// ---- KPIs ----
function kpis(rows,id){
  const total=rows.reduce((s,r)=>s+val(r),0);
  const mset=new Set(rows.map(r=>r.m));const nM=mset.size||1;
  const byCat={},byCard={};
  rows.forEach(r=>{byCat[r.g]=(byCat[r.g]||0)+val(r);byCard[r.c]=(byCard[r.c]||0)+val(r);});
  const tc=Object.entries(byCat).sort((a,b)=>b[1]-a[1])[0]||["–",0];
  const tk=Object.entries(byCard).sort((a,b)=>b[1]-a[1])[0]||["–",0];
  const K=[["Total spend",fmt(total),svgIcon("wallet-outline")],["Avg / month",fmt(total/nM),svgIcon("chart-line")],["Transactions",rows.length.toLocaleString(),svgIcon("counter")],
    ["Top category",`<small>${tc[0]}</small><br>${fmtk(tc[1])}`,svgIcon((D.catIcon&&D.catIcon[tc[0]])||"shape-outline")],["Top card",`<small>${tk[0]}</small><br>${fmtk(tk[1])}`,svgIcon("credit-card-outline")]];
  document.getElementById(id).innerHTML=K.map(k=>`<div class="kpi"><div class="lab">${k[2]||""}${k[0]}</div><div class="val">${k[1]}</div></div>`).join("");
}

// ---- monthly stacked bar ----
function trend(rows){
  const cats=activeCats(),M=D.months;
  const stack={};M.forEach(m=>stack[m]={});
  rows.forEach(r=>stack[r.m][r.g]=(stack[r.m][r.g]||0)+val(r));
  const tot=M.map(m=>cats.reduce((s,g)=>s+(stack[m][g]||0),0));
  const max=Math.max(1,...tot);
  const W=1180,H=300,L=54,B=46,T=10,R=10,iw=W-L-R,ih=H-B-T;
  const s=el("svg",{viewBox:`0 0 ${W} ${H}`});
  for(let i=0;i<=4;i++){const y=T+ih*i/4,v=max*(1-i/4);
    s.appendChild(el("line",{x1:L,y1:y,x2:W-R,y2:y,class:"axis","stroke-dasharray":i?"2 4":"0"}));
    const tx=el("text",{x:L-8,y:y+4,"text-anchor":"end"});tx.textContent=fmtk(v);s.appendChild(tx);}
  const bw=iw/M.length*0.66,gap=iw/M.length;
  M.forEach((m,i)=>{
    let y=T+ih,x=L+gap*i+(gap-bw)/2;
    cats.forEach(g=>{const v=stack[m][g]||0;if(v<=0)return;const h=v/max*ih;y-=h;
      const rc=el("rect",{x,y,width:bw,height:h,fill:C[g],rx:1});
      tip(rc,`<b>${m}</b> · ${g}<br>${fmt(v)}`);
      s.appendChild(rc);});
    const tx=el("text",{x:x+bw/2,y:H-B+16,"text-anchor":"middle"});tx.textContent=m.slice(2);s.appendChild(tx);
    const tv=el("text",{x:x+bw/2,y:y-5,"text-anchor":"middle","font-size":"9"});tv.textContent=fmtk(tot[i]);tv.setAttribute("fill","#aeb9c7");s.appendChild(tv);
  });
  swap("trend",s);
  document.getElementById("t-trend").textContent=fmt(tot.reduce((a,b)=>a+b,0))+" total";
  document.getElementById("trendlg").innerHTML=cats.map(g=>`<span>${catIcon(g)}${g}</span>`).join("");
}

// ---- horizontal bar by card ----
function byCard(rows,id){
  const by={};rows.forEach(r=>by[r.c]=(by[r.c]||0)+val(r));
  const data=Object.entries(by).sort((a,b)=>b[1]-a[1]);
  hbar(id,data,d=>pickCardColor(d[0]),true);
}

// ---- donut ----
function donut(rows,id,labid){
  const by={};rows.forEach(r=>by[r.g]=(by[r.g]||0)+val(r));
  const data=Object.entries(by).filter(d=>d[1]>0.005).sort((a,b)=>b[1]-a[1]);
  const tot=data.reduce((s,d)=>s+d[1],0)||1;
  const W=420,H=300,cx=116,cy=150,r0=56,r1=100;
  const s=el("svg",{viewBox:`0 0 ${W} ${H}`});
  let a0=-Math.PI/2;
  data.forEach(d=>{const frac=d[1]/tot,a1=a0+frac*2*Math.PI;
    s.appendChild(arc(cx,cy,r0,r1,a0,a1,C[d[0]],d,tot));a0=a1;});
  const c=el("text",{x:cx,y:cy-2,"text-anchor":"middle","font-size":"18",fill:"#e6edf3","font-weight":"700"});c.textContent=fmtk(tot);s.appendChild(c);
  const c2=el("text",{x:cx,y:cy+15,"text-anchor":"middle"});c2.textContent="total";s.appendChild(c2);
  // legend right column: swatch · name (clamped so it never collides with the % at the right edge) · %
  const clip=t=>t.length>17?t.slice(0,16)+"…":t;
  data.slice(0,8).forEach((d,i)=>{const y=44+i*26;
    s.appendChild(el("rect",{x:236,y:y-9,width:11,height:11,rx:2,fill:C[d[0]]}));
    const t1=el("text",{x:252,y:y});t1.textContent=clip(d[0]);t1.setAttribute("fill","#cdd6e0");s.appendChild(t1);
    const t2=el("text",{x:W,y:y,"text-anchor":"end","font-weight":"600"});t2.textContent=(d[1]/tot*100).toFixed(0)+"%";t2.setAttribute("fill","#e6edf3");s.appendChild(t2);});
  swap(id,s);
  document.getElementById(labid).textContent=data.length+" categories";
}
function arc(cx,cy,r0,r1,a0,a1,fill,d,tot){
  const p=(r,a)=>[cx+r*Math.cos(a),cy+r*Math.sin(a)];
  const big=a1-a0>Math.PI?1:0;
  const[x0,y0]=p(r1,a0),[x1,y1]=p(r1,a1),[x2,y2]=p(r0,a1),[x3,y3]=p(r0,a0);
  const path=el("path",{d:`M${x0},${y0} A${r1},${r1} 0 ${big} 1 ${x1},${y1} L${x2},${y2} A${r0},${r0} 0 ${big} 0 ${x3},${y3} Z`,fill});
  tip(path,`<b>${d[0]}</b><br>${fmt(d[1])} · ${(d[1]/tot*100).toFixed(1)}%`);return path;
}

// ---- heatmap card x category ----
function heat(rows){
  const cats=activeCats(),cards=D.cards.filter(c=>selCards.has(c));
  const cell={};let max=0;
  rows.forEach(r=>{const k=r.c+"|"+r.g;cell[k]=(cell[k]||0)+val(r);if(cell[k]>max)max=cell[k];});
  const L=120,T=8,cw=Math.max(46,(1180-L)/cats.length),ch=30,W=L+cw*cats.length,H=T+ch*cards.length+70;
  const s=el("svg",{viewBox:`0 0 ${W} ${H}`});
  cats.forEach((g,j)=>{const x=L+cw*j;
    const t=el("text",{x:x+cw/2,y:T+ch*cards.length+16,"text-anchor":"end","transform":`rotate(-35 ${x+cw/2} ${T+ch*cards.length+16})`});
    t.textContent=g;s.appendChild(t);});
  cards.forEach((c,i)=>{const y=T+ch*i;
    const t=el("text",{x:L-8,y:y+ch/2+4,"text-anchor":"end",fill:"#cdd6e0"});t.textContent=c;s.appendChild(t);
    cats.forEach((g,j)=>{const x=L+cw*j,v=cell[c+"|"+g]||0,a=max>0?Math.max(0,Math.min(1,v/max)):0;
      const rc=el("rect",{x:x+1,y:y+1,width:cw-2,height:ch-2,rx:3,fill:v>0?mix(a,C[g]):"#10151b"});
      if(v>0){tip(rc,`<b>${c}</b> · ${g}<br>${fmt(v)}`);
        if(a>0.18){const tv=el("text",{x:x+cw/2,y:y+ch/2+4,"text-anchor":"middle","font-size":"10",fill:a>0.55?"#0b0e12":"#cdd6e0"});tv.textContent=fmtk(v);s.appendChild(tv);}}
      s.appendChild(rc);});});
  swap("heat",s);
}
function mix(a,hex){const n=parseInt(hex.slice(1),16),r=n>>16,g=n>>8&255,b=n&255,k=0.22+0.78*a;
  const bg=[16,21,27];return`rgb(${Math.round(bg[0]+(r-bg[0])*k)},${Math.round(bg[1]+(g-bg[1])*k)},${Math.round(bg[2]+(b-bg[2])*k)})`;}

// ---- top merchants ----
function merch(rows){
  const by={};rows.forEach(r=>{by[r.d]=(by[r.d]||0)+val(r);});
  const data=Object.entries(by).filter(d=>d[1]>0.005).sort((a,b)=>b[1]-a[1]).slice(0,20);
  hbar("merch",data,()=>"#60a5fa",false);
}

// ---- generic horizontal bar ----
function hbar(id,data,colorFn,clickable){
  const max=Math.max(1,...data.map(d=>d[1]));
  // W is in viewBox units; the svg scales to the (half-width) card, so a smaller W = larger
  // rendered text. 1180 made the non-clickable cashback bars' labels shrink to ~4px — use 470.
  const L=clickable?150:175,rh=26,W=clickable?560:470,H=Math.max(40,data.length*rh+8),bw=W-L-70;
  const s=el("svg",{viewBox:`0 0 ${W} ${H}`});
  data.forEach((d,i)=>{const y=i*rh+4,w=Math.max(0,d[1])/max*bw;
    const lab=el("text",{x:L-8,y:y+rh/2+1,"text-anchor":"end",fill:"#cdd6e0"});lab.textContent=d[0];s.appendChild(lab);
    const rc=el("rect",{x:L,y:y+3,width:w,height:rh-9,rx:3,fill:colorFn(d)});
    if(clickable)tip(rc,`<b>${d[0]}</b><br>${fmt(d[1])}`,()=>{selCards.clear();selCards.add(d[0]);syncChips();render();});
    else tip(rc,`<b>${d[0]}</b><br>${fmt(d[1])}`);
    s.appendChild(rc);
    const v=el("text",{x:L+w+6,y:y+rh/2+1});v.textContent=fmtk(d[1]);s.appendChild(v);});
  swap(id,s);
}

// ===================== Monthly view =====================
function monthRows(m){return D.rows.filter(r=>selCards.has(r.c)&&r.m===m);}            // all types
function monthSpend(m){return monthRows(m).filter(r=>(mode==="all"||!NS.has(r.g))&&!(NS.has(r.g)&&r.t===1));}

function renderMonthly(){
  if(!curMonth)return;
  buildMonthNav();
  const m=curMonth,rows=monthSpend(m);
  heroBand(m);
  monthKpis(m,rows);
  byCard(rows,"mcard");
  donut(rows,"mdonut","t-mdonut");
  mom(m);
  table(m);
}

function buildMonthNav(){
  const sel=document.getElementById("monthsel");
  if(sel.dataset.built!=="1"){
    sel.innerHTML=D.months.map(m=>`<option value="${m}">${m}</option>`).join("");
    sel.dataset.built="1";
    sel.onchange=()=>{curMonth=sel.value;renderMonthly();};
  }
  sel.value=curMonth;
}

function monthDelta(m){
  const total=monthSpend(m).reduce((s,r)=>s+val(r),0);
  const i=D.months.indexOf(m),pm=i>0?D.months[i-1]:null;
  const prev=pm?monthSpend(pm).reduce((s,r)=>s+val(r),0):null;
  const d=prev==null?null:total-prev, pc=(prev?d/prev*100:null);
  return {total,prev,pm,d,pc};
}
function monthCashback(m){
  return monthRows(m).filter(r=>r.t===1&&r.g==="Rebate/Cashback").reduce((s,r)=>s+r.a,0);
}
function monthCatMerchants(m,pm,g){
  const cur={},prev={};
  D.rows.filter(r=>selCards.has(r.c)&&r.g===g&&(mode==="all"||!NS.has(r.g))&&!(NS.has(r.g)&&r.t===1)).forEach(r=>{
    if(r.m===m)cur[r.d]=(cur[r.d]||0)+val(r);
    else if(pm&&r.m===pm)prev[r.d]=(prev[r.d]||0)+val(r);});
  const keys=new Set([...Object.keys(cur),...Object.keys(prev)]);
  const out=[...keys].map(k=>({d:k,prev:prev[k]||0,cur:cur[k]||0,delta:(cur[k]||0)-(prev[k]||0)}));
  out.sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));
  return out.slice(0,6);
}
function movers(m){
  const i=D.months.indexOf(m),pm=i>0?D.months[i-1]:null;
  if(!pm)return `<div class="movers"><div class="lab">${svgIcon("swap-vertical")} Movers vs last month</div><div class="ln" style="color:var(--mut)">First month in range — nothing to compare.</div></div>`;
  const cur={},prev={};
  monthSpend(m).forEach(r=>cur[r.g]=(cur[r.g]||0)+val(r));
  monthSpend(pm).forEach(r=>prev[r.g]=(prev[r.g]||0)+val(r));
  const diffs=activeCats().map(g=>({g,delta:(cur[g]||0)-(prev[g]||0)})).filter(d=>Math.abs(d.delta)>=0.01);
  const rises=diffs.filter(d=>d.delta>0).sort((a,b)=>b.delta-a.delta).slice(0,3);
  const drop=diffs.filter(d=>d.delta<0).sort((a,b)=>a.delta-b.delta)[0];
  const picks=[...rises]; if(drop)picks.push(drop);
  if(!picks.length)return `<div class="movers"><div class="lab">${svgIcon("swap-vertical")} Movers vs last month</div><div class="ln" style="color:var(--mut)">No category changes vs last month.</div></div>`;
  const rows=picks.map(d=>{
    const up=d.delta>0,col=up?"var(--red)":"var(--green)";
    const md=monthCatMerchants(m,pm,d.g);
    const det=`<table class="dtbl"><thead><tr><th>Merchant</th><th class="num">${pm.slice(2)}</th><th class="num">${m.slice(2)}</th><th class="num">Δ</th></tr></thead><tbody>`+
      md.map(x=>`<tr><td>${esc(x.d)}</td><td class="num">${fmt(x.prev)}</td><td class="num">${fmt(x.cur)}</td>`+
        `<td class="num" style="color:${x.delta>=0?'var(--red)':'var(--green)'}">${x.delta>=0?'+':'−'}${fmt(Math.abs(x.delta))}</td></tr>`).join("")+
      `</tbody></table>`;
    return `<div class="mvrow" role="button" tabindex="0" aria-expanded="false">`+
      `<div class="mvhead"><span class="nm">${catIcon(d.g)}${esc(d.g)}</span>`+
      `<span class="d" style="color:${col}">${up?'+':'−'}${fmtk(Math.abs(d.delta))} vs last month</span></div>`+
      `<div class="detail">${det}</div></div>`;
  }).join("");
  return `<div class="movers"><div class="lab">${svgIcon("swap-vertical")} Movers vs last month</div>${rows}</div>`;
}
function heroBand(m){
  const {total,d,pc,pm}=monthDelta(m);
  let delta="<div class=\"delta\">No previous month to compare.</div>";
  if(d!=null){const cls=d>=0?"up":"down",arr=d>=0?"▲":"▼";
    const pcs=pc==null?"new":`${pc>=0?"+":""}${pc.toFixed(0)}%`;
    delta=`<div class="delta ${cls}">${arr} ${fmt(Math.abs(d))} (${pcs}) vs ${pm.slice(2)}</div>`;}
  const cb=monthCashback(m);
  document.getElementById("hero").innerHTML=
    `<div class="head"><div class="lab">${svgIcon("wallet-outline")} Spend this month · ${m}</div>`+
    `<div class="big">${fmt(total)}</div>${delta}</div>`+
    `<div class="cb"><div class="lab">${svgIcon("cash-plus")} Cashback earned</div><div class="amt">${fmt(cb)}</div></div>`+
    movers(m)+
    cutCandidates(m);
}
function monthKpis(m,rows){
  const byCat={};rows.forEach(r=>byCat[r.g]=(byCat[r.g]||0)+val(r));
  const tc=Object.entries(byCat).sort((a,b)=>b[1]-a[1])[0]||["–",0];
  const big=rows.filter(r=>!r.t).sort((a,b)=>b.a-a.a)[0];
  const K=[["Transactions",rows.length,svgIcon("counter")],
    ["Biggest txn",big?`<small>${esc(big.d)}</small><br>${fmt(big.a)}`:"–",svgIcon("receipt-text-outline")],
    ["Top category",`<small>${tc[0]}</small><br>${fmtk(tc[1])}`,svgIcon((D.catIcon&&D.catIcon[tc[0]])||"shape-outline")]];
  document.getElementById("mkpis").innerHTML=K.map(k=>`<div class="kpi"><div class="lab">${k[2]||""}${k[0]}</div><div class="val">${k[1]}</div></div>`).join("");
}

function mom(m){
  const i=D.months.indexOf(m),pm=i>0?D.months[i-1]:null,W=1180;
  if(!pm){const s=el("svg",{viewBox:`0 0 ${W} 56`});const t=el("text",{x:W/2,y:32,"text-anchor":"middle"});
    t.textContent="First month in range — nothing to compare against.";s.appendChild(t);swap("mom",s);return;}
  const cur={},prev={};
  monthSpend(m).forEach(r=>cur[r.g]=(cur[r.g]||0)+val(r));
  monthSpend(pm).forEach(r=>prev[r.g]=(prev[r.g]||0)+val(r));
  const diffs=activeCats().map(g=>[g,(cur[g]||0)-(prev[g]||0)]).filter(d=>Math.abs(d[1])>=0.01).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1]));
  if(!diffs.length){const s=el("svg",{viewBox:`0 0 ${W} 56`});const t=el("text",{x:W/2,y:32,"text-anchor":"middle"});
    t.textContent="No category change vs previous month.";s.appendChild(t);swap("mom",s);return;}
  const H=Math.max(56,diffs.length*30+18),L=160,R=80,cx=L+(W-L-R)/2,half=(W-L-R)/2;
  const max=Math.max(1,...diffs.map(d=>Math.abs(d[1])));
  const s=el("svg",{viewBox:`0 0 ${W} ${H}`});
  s.appendChild(el("line",{x1:cx,y1:4,x2:cx,y2:H-12,class:"axis"}));
  diffs.forEach((d,j)=>{const y=8+j*30,w=Math.abs(d[1])/max*half,up=d[1]>0,x=up?cx:cx-w,col=up?"#ef4444":"#34d399";
    const lab=el("text",{x:L-10,y:y+14,"text-anchor":"end",fill:"#cdd6e0"});lab.textContent=d[0];s.appendChild(lab);
    const rc=el("rect",{x,y:y+3,width:w,height:18,rx:3,fill:col});
    tip(rc,`<b>${d[0]}</b><br>${pm.slice(2)}: ${fmt(prev[d[0]]||0)} → ${m.slice(2)}: ${fmt(cur[d[0]]||0)}<br>${up?"+":"−"}${fmt(Math.abs(d[1]))}`);s.appendChild(rc);
    // value label sits just past the bar's tip on the OUTER side; for a decrease the bar can reach
    // the left axis margin (=L) where the category label lives, so put the −value to the right of
    // the centre axis (that row's right zone is empty) instead of colliding with the gutter.
    const v=el("text",{x:up?x+w+6:cx+6,y:y+15,"text-anchor":"start",fill:col});v.textContent=(up?"+":"−")+fmtk(Math.abs(d[1]));s.appendChild(v);});
  swap("mom",s);
}

let sortKey="a",sortDir=-1;
function table(m){
  const rows=monthRows(m).slice();
  rows.sort((a,b)=>{const x=a[sortKey],y=b[sortKey];return sortDir*(typeof x==="number"?x-y:String(x).localeCompare(String(y)));});
  const cols=[["c","Card"],["d","Description"],["g","Category"],["t","Type"],["a","Amount","num"]];
  let h="<thead><tr>"+cols.map(c=>`<th class="${c[2]||''}" data-k="${c[0]}">${c[1]}</th>`).join("")+"</tr></thead><tbody>";
  rows.forEach(r=>{h+=`<tr><td>${r.c}</td><td>${esc(r.d)}</td>`+
    `<td><span class="tag" style="background:${C[r.g]}22;color:${C[r.g]}">${svgIcon((D.catIcon&&D.catIcon[r.g])||"shape-outline")} ${r.g}</span></td>`+
    `<td class="${r.t?'cr':''}">${r.t?'credit':'debit'}</td>`+
    `<td class="num ${r.t?'cr':''}">${r.t?'−':''}${fmt(r.a)}</td></tr>`;});
  h+="</tbody>";
  const t=document.getElementById("mtbl");t.innerHTML=h;
  t.querySelectorAll("th").forEach(th=>{
    th.tabIndex=0;
    if(th.dataset.k===sortKey)th.setAttribute("aria-sort",sortDir<0?"descending":"ascending");
    const sort=()=>{const k=th.dataset.k;if(sortKey===k)sortDir*=-1;else{sortKey=k;sortDir=(k==="a")?-1:1;}table(m);};
    th.onclick=sort;
    th.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();sort();}});});
  document.getElementById("t-mtbl").textContent=rows.length+" rows";
}

function gotoRecs(){
  view="recs";
  document.querySelectorAll("#view button").forEach(x=>x.classList.toggle("on",x.dataset.v==="recs"));
  document.getElementById("view-overview").classList.toggle("on",false);
  document.getElementById("view-monthly").classList.toggle("on",false);
  document.getElementById("view-recs").classList.toggle("on",true);
  render();
}
function cutTouchesMonth(r,m){
  if(r.type==="sub")return (r.evidence||[]).some(e=>e.m===m);
  if(r.type==="oneoff")return r.month===m;
  if(r.type==="creep"){const last3=new Set(D.months.slice(-3));return last3.has(m);}
  return false;
}
function cutCandidates(m){
  const cards=new Set([...selCards]);
  const picks=(D.recs&&D.recs.recs?D.recs.recs:[])
    .filter(r=>recVisible(r,cards)&&cutTouchesMonth(r,m))
    .sort((a,b)=>b.rmAnnual-a.rmAnnual).slice(0,4);
  if(!picks.length)return `<div class="cuts"><div class="lab">${svgIcon("content-cut")} Cut candidates this month</div><div class="ln" style="color:var(--mut)">No leaks detected for this month.</div></div>`;
  const rows=picks.map(r=>
    `<div class="cutrow rectype-${r.type}" role="button" tabindex="0">`+
    `<div><div class="ttl">${esc(r.title)}</div><div class="ln">${esc(r.line)}</div></div>`+
    `<div class="badge">${fmtk(r.rmAnnual)}<br><span class="ln">/yr</span><span class="arrow">›</span></div></div>`).join("");
  return `<div class="cuts"><div class="lab">${svgIcon("content-cut")} Cut candidates this month <span class="ln">click → Recommendations</span></div>${rows}</div>`;
}

// ===================== Recommendations view =====================
function renderRecs(){
  const cards=new Set([...selCards]);
  const vis=it=>!it.evidence||!it.evidence.length||it.evidence.some(e=>cards.has(e.c));
  const all=D.recs.recs.filter(r=>recVisible(r,cards));
  const subs=all.filter(r=>r.type==="sub"), creep=all.filter(r=>r.type==="creep"), oo=all.filter(r=>r.type==="oneoff");
  const inst=(D.recs.installments||[]).filter(vis), xfer=(D.recs.transfers||[]).filter(vis);
  const save=subs.reduce((s,r)=>s+r.rmAnnual,0)+creep.reduce((s,r)=>s+r.rmAnnual,0);
  const instMo=inst.reduce((s,p)=>s+p.monthly,0), xferMo=xfer.reduce((s,t)=>s+t.monthly,0);
  const K=[["Potential savings",fmt(save)+"<small> /yr</small>","piggy-bank-outline"],
    ["Subscriptions",subs.length+"<small> cancellable</small>","sync"],
    ["Installments",inst.length+`<small> · ${fmtk(instMo)}/mo</small>`,"calendar-clock"],
    ["Balance transfers",xfer.length+`<small> · ${fmtk(xferMo)}/mo</small>`,"bank-transfer"],
    ["Big one-offs",oo.length+"<small> this/last mo</small>","alert-circle"]];
  document.getElementById("reckpis").innerHTML=K.map(k=>`<div class="kpi"><div class="lab">${svgIcon(k[2])}${k[0]}</div><div class="val">${k[1]}</div></div>`).join("");
  const sec=(t,html,ic)=>html?`<div class="recsec">${ic?svgIcon(ic,"seci"):""}${t}</div>`+html:"";
  const g=document.getElementById("recgrid");
  const body=
    sec("Subscriptions — cancel candidates",subs.map(recCard).join(""),"sync")+
    sec("Installments — fixed term",inst.map(instCard).join(""),"calendar-clock")+
    sec("Balance transfers — debt consolidation",xfer.map(xferCard).join(""),"bank-transfer")+
    sec(`Creeping categories — watch`,creep.map(recCard).join(""),"trending-up")+
    sec("Big one-offs — was it planned?",oo.map(recCard).join(""),"alert-circle");
  g.innerHTML=body||`<div class="sub" style="grid-column:1/-1">No leaks detected for the selected cards. Spend looks controlled.</div>`;
}
function recVisible(r,cards){
  // sub/oneoff carry evidence rows with a card; creep has none -> always visible
  if(r.type==="creep")return true;
  if(r.evidence&&r.evidence.length)return r.evidence.some(e=>cards.has(e.c));
  return true;
}
function recCard(r){
  const stale=r.stale?`<span class="stalebadge">last ${r.last} · cancelled?</span>`:"";
  const cc=C[r.cat]||"#64748b";
  const cat=r.cat?`<span class="catchip" style="background:${cc}22;color:${cc}">${svgIcon((D.catIcon&&D.catIcon[r.cat])||"shape-outline")} ${esc(r.cat)}</span>`:"";
  return `<div class="rec rectype-${r.type}${r.stale?' stale':''}" role="button" tabindex="0" aria-expanded="false">`+
    `<div class="rechead"><div><div class="ttl"><span class="car">▸</span> ${esc(r.title)}${cat}${stale}</div>`+
    `<div class="ln">${esc(r.line)}</div><span class="hint">${esc(r.hint)}</span></div>`+
    `<div class="badge">${fmtk(r.rmAnnual)}<br><span class="ln">/yr</span></div></div>`+
    `<div class="detail">${recDetail(r)}</div></div>`;
}
function recDetail(r){
  const ev=r.evidence||[];
  if(r.type==="sub"){
    if(!ev.length)return `<div class="ln">No charge rows.</div>`;
    const rows=ev.slice().sort((a,b)=>a.m<b.m?-1:1);
    const note=r.stale?`Silent for ${r.lastGap} month(s) since ${r.last} — likely already cancelled.`:`Last charged ${r.last} · active.`;
    return `<table class="dtbl"><thead><tr><th>Month</th><th>Card</th><th class="num">Amount</th></tr></thead><tbody>`+
      rows.map(e=>`<tr class="${e.m===r.last?'last':''}"><td>${e.m}</td><td>${esc(e.c)}</td><td class="num">${fmt(e.a)}</td></tr>`).join("")+
      `</tbody></table><div class="ln" style="margin-top:6px">${note}</div>`;
  }
  if(r.type==="creep"){
    if(!ev.length)return `<div class="ln">No merchant breakdown.</div>`;
    return `<table class="dtbl"><thead><tr><th>Merchant</th><th class="num">Prev 3mo</th><th class="num">Last 3mo</th><th class="num">Δ</th></tr></thead><tbody>`+
      ev.map(e=>`<tr><td>${esc(e.merchant)}</td><td class="num">${fmt(e.prev)}</td><td class="num">${fmt(e.recent)}</td>`+
        `<td class="num" style="color:${e.delta>=0?'var(--red)':'var(--green)'}">${e.delta>=0?'+':'−'}${fmt(Math.abs(e.delta))}</td></tr>`).join("")+
      `</tbody></table>`;
  }
  const e=ev[0]||{};
  return `<table class="dtbl"><tbody>`+
    `<tr><td>Description</td><td>${esc(r.merchant||"")}</td></tr>`+
    `<tr><td>Month</td><td>${r.month||""}</td></tr>`+
    `<tr><td>Card</td><td>${esc(r.c||e.c||"")}</td></tr>`+
    `<tr><td>Category</td><td>${esc(r.cat||"")}</td></tr>`+
    `<tr><td class="num">Amount</td><td class="num">${fmt(r.amount||0)}</td></tr>`+
    `<tr><td>Vs norm</td><td>${r.mult}× category median</td></tr></tbody></table>`;
}

function histTable(ev,last){
  if(!ev||!ev.length)return `<div class="ln">No rows.</div>`;
  const rows=ev.slice().sort((a,b)=>a.m<b.m?-1:1);
  return `<table class="dtbl"><thead><tr><th>Month</th><th>Card</th><th class="num">Amount</th></tr></thead><tbody>`+
    rows.map(e=>`<tr class="${e.m===last?'last':''}"><td>${e.m}</td><td>${esc(e.c)}</td><td class="num">${fmt(e.a)}</td></tr>`).join("")+
    `</tbody></table>`;
}
function instCard(p){
  const cc=C[p.cat]||"#9ca3af";
  const cat=`<span class="catchip" style="background:${cc}22;color:${cc}">${svgIcon((D.catIcon&&D.catIcon[p.cat])||"shape-outline")} ${esc(p.cat)}</span>`;
  const parts=[];
  if(p.term)parts.push(p.progressN!=null?`${p.progressN} of ${p.term} paid`:`${p.term}-mo plan`);
  if(p.remaining!=null)parts.push(`${p.est?"~":""}${p.remaining} mo left`);
  if(p.remainBal!=null)parts.push(`${fmtk(p.remainBal)} to go`);
  const line=parts.join(" · ")||"term unknown";
  const endbit=p.ended?`<span class="stalebadge">ended ${p.last}</span>`
    :(p.endMonth?`<span class="hint">${p.est?"est. ":""}ends ${p.endMonth}</span>`:"");
  return `<div class="rec rectype-installment${p.ended?' stale':''}" role="button" tabindex="0" aria-expanded="false">`+
    `<div class="rechead"><div><div class="ttl"><span class="car">▸</span> ${esc(p.name)}${cat}</div>`+
    `<div class="ln">${esc(line)}</div>${endbit}</div>`+
    `<div class="badge">${fmtk(p.monthly)}<br><span class="ln">/mo</span></div></div>`+
    `<div class="detail">${histTable(p.evidence,p.last)}</div></div>`;
}
function xferCard(t){
  return `<div class="rec rectype-transfer${t.ended?' stale':''}" role="button" tabindex="0" aria-expanded="false">`+
    `<div class="rechead"><div><div class="ttl"><span class="car">▸</span> ${esc(t.name)}</div>`+
    `<div class="ln">${fmtk(t.paidInWindow)} paid in-window · last ${t.last}</div></div>`+
    `<div class="badge">${fmtk(t.monthly)}<br><span class="ln">/mo</span></div></div>`+
    `<div class="detail">${histTable(t.evidence,t.last)}</div></div>`;
}
function swap(id,s){const old=document.getElementById(id);s.id=id;
  // expose the chart to assistive tech as a labelled group named after its card heading.
  s.setAttribute("role","group");
  const card=old&&old.closest&&old.closest(".card"),h2=card&&card.querySelector&&card.querySelector("h2");
  if(h2&&h2.textContent)s.setAttribute("aria-label",h2.textContent.replace(/\s+/g," ").trim());
  old.replaceWith(s);}
render();
</script></body></html>
"""

if __name__ == "__main__":
    if not os.path.exists(SRC):
        raise SystemExit(f"{SRC} not found -- run parse.py first")
    build()
