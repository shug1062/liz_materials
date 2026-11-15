# Studio page map

Verified against the app routes and templates on 15 November 2026.

Mermaid is a good fit for this map: it is editable text, can live alongside the
code, and renders on GitHub and in Markdown viewers with Mermaid support.
The map is split into connected sections to avoid one unreadably large graph.
Repeated page names refer to the same page, not duplicate implementations.
The PNG is an older export; this Mermaid source reflects the unified register.

**Legend:** solid arrows are links to pages; dotted arrows are in-page features,
external destinations, or return paths as labelled. Add/edit screens sharing a
form are grouped. Filters, tabs and selected dates are states of a page, not
separate pages. The shared menu is shown once rather than repeated everywhere.

## 1. Shared menu and main pages

The signed-in app pages share this menu. The logo also returns to Class register.

```mermaid
flowchart TB
    Menu["Shared navigation on app pages"]
    Menu --> Register["Class register<br/>/ or /class/"]
    Menu --> Dashboard["Dashboard<br/>/dashboard/"]
    Register --> Students["All students / account overview<br/>/students/"]
    Register --> Classes["Manage classes<br/>/classes/"]
    Menu --> Purchase["Record purchase - choose student<br/>/purchases/new/"]
    Menu --> Payments["Payments<br/>/payments/"]
    Menu --> Sales["Sales<br/>/sales/"]
    Menu --> Reports["Reports<br/>/reports/"]
    Menu --> Materials["Materials<br/>/materials/"]
    Menu --> Projects["Projects<br/>/projects/"]
    Menu --> Settings["Settings<br/>/settings/"]
    Settings --> Admin["Django admin<br/>/admin/"]
    Login["Login - when login is required<br/>/login/"] -.->|Successful login, default destination| Dashboard
    Menu -.->|Log out, when enabled| Login
    Legacy["Legacy /profit/ URL"] -.->|Redirect| Reports
```

## 2. Students, class register and purchases

**All students → Purchase**, **Account & history → Record purchase**, and
**Class register → Class → Student** all open the **same shared basket**.
The main menu's **Record purchase** asks you to select a student, then opens
the same basket. Existing purchases retain their individual edit form.

```mermaid
flowchart LR
    Register["Class register: choose a class<br/>Current/upcoming, all or finished; includes empty classes"]
    Class["Class register: students in selected class<br/>/class/?class_name=..."]
    Students["All students / class account overview<br/>/students/"]
    Details["Student: Account & history<br/>/students/ID/"]
    Basket["SHARED student basket<br/>/class/student/ID/"]
    StudentForm["Student: Details / add student<br/>/students/add/ or /students/ID/edit/"]
    Payment["Record payment form<br/>/payments/new/"]
    Purchase["Choose student for purchase<br/>/purchases/new/"]
    PurchaseEdit["Edit existing purchase<br/>/purchases/ID/edit/"]
    PaymentEdit["Edit existing payment<br/>/payments/ID/edit/"]
    Sale["Record a sale<br/>/sales/new/"]
    SaleEdit["Edit existing sale<br/>/sales/ID/edit/"]
    Statement["Student statement<br/>/students/ID/statement/"]
    Email["External email app"]
    Archived["Archived students<br/>/students/archived/"]
    Import["Import from Wix: upload and preview<br/>/students/import/"]
    Merge["Merge student records: select and confirm<br/>/students/ID/merge/"]
    Balances["Balances to chase<br/>/balances/"]
    Classes["Classes management"]

    Register -->|Choose class| Class
    Register --> Students
    Register --> Archived
    Register --> Import
    Register --> Classes
    Register -->|Add student| StudentForm
    Class -->|Account overview| Students
    Class -->|Add student| StudentForm
    Class -->|Manage class| Management["Class details / membership<br/>/classes/ID/"]
    Class -->|Class summary| Day["Class summary by date"]
    Class -->|Add project| ProjectPicker["Select project, then review class material quantities"]
    Class -->|Choose student| Basket
    Class --> Sale
    Class -->|Other classes| Register
    Students -->|Purchase| Basket
    Students -->|Student name| Details
    Students -->|Class register| Class
    Students -->|Add student / Edit| StudentForm
    Students -->|Payment| Payment
    Students --> Archived
    Students --> Import
    Students --> Balances
    Students --> Classes
    Students -.->|Email statement| Email
    Archived --> Details
    Details -->|Record purchase| Basket
    Details -->|Record payment| Payment
    Details --> Sale
    Details --> StudentForm
    StudentForm --> Merge
    StudentForm -.->|Archive / restore / delete| AdminActions["Student administration"]
    Details --> Statement
    Details -->|Purchase history: Edit| PurchaseEdit
    Details -->|Payment history: Edit| PaymentEdit
    Details -->|Sales history: Edit| SaleEdit
    Details -->|Back to register| Class
    Details -.->|Email statement| Email
    Basket -->|Pay cash / Pay card| Payment
    Basket -->|Account & history tab| Details
    Basket -->|Details tab| StudentForm
    StudentForm -->|Materials tab| Basket
    Basket -->|Past purchases: Edit| PurchaseEdit
    Basket -.-> Features["On this same page:<br/>Quick add, material search, multi-item basket,<br/>purchase note, date and project,<br/>record a payment, purchase history"]
    Basket -.->|Save basket / Cancel| Origin["Class register by default,<br/>or explicit return destination"]
    Payment -.->|Save / Cancel from basket| Basket
    StudentForm -.->|Edit from Students: Save / Cancel| Students
    StudentForm -.->|Default Save / Cancel| Class
    Purchase -->|Select student| Basket
    Basket -.->|Save / Cancel when opened from chooser| Purchase
    PurchaseEdit -.->|Save / Cancel| History["Originating purchase-history page"]
    PaymentEdit -.->|Save / Cancel| PaymentHistory["Originating payment-history page"]
    Balances --> Details
    Balances --> Statement
    Balances -->|Add email| StudentForm
    Balances -.->|Email| Email
    Statement --> Details
    Statement -->|Add missing email| StudentForm
    Statement -.->|Email statement| Email
```

- Cash and card links open one payment form, with the method selected and the
  amount blank. The form has £5, £10 and £20–£100 amount shortcuts (in £10 steps);
  Save confirms.
- Both links are available for students with debt, zero balance or credit.
- The basket has one purchase note copied to every new basket item. Its payment
  notes are separate.
- Return destinations use the validated `next` parameter where provided.
  For example, All students' Purchase button returns to that student's register,
  while Edit preserves the current account-overview filter.
- Student pages share Materials, Account & history and Details tabs.
  Default saves return to the relevant register; archived students and sales
  channels retain their own reachable overview. Not every return arrow is drawn.

## 3. Class administration

Class administration is a subordinate part of Class register; the working
forms remain separate so their existing behaviour and data are preserved.

```mermaid
flowchart LR
    Classes["Manage classes<br/>/classes/"]
    ClassDetails["Manage class / membership<br/>/classes/ID/"]
    ClassForm["Add / edit class<br/>/classes/add/ or /classes/ID/edit/"]
    Dates["Set term dates<br/>/classes/dates/"]
    Review["Review and archive students<br/>/classes/archive/"]
    Archived["Archived students<br/>/students/archived/"]
    Fee["Charge course fee<br/>/classes/ID/charge/"]
    Term["Copy for next term<br/>/classes/ID/next-term/"]
    Day["Class summary by date<br/>/classes/ID/day/"]
    RegisterClass["Selected class register"]
    Student["Student details"]
    NewStudent["Add student"]

    Classes --> ClassDetails
    Classes -->|New class| ClassForm
    Classes --> Dates
    Classes --> Review
    Classes --> Archived
    RegisterClass -->|Manage class| ClassDetails
    RegisterClass --> Day
    ClassDetails -->|Edit class| ClassForm
    ClassDetails --> Fee
    ClassDetails --> Term
    ClassDetails --> Day
    ClassDetails --> RegisterClass
    ClassDetails --> Student
    ClassDetails --> NewStudent
    ClassDetails -.-> Membership["Inline search and add existing student"]
    ClassDetails -.-> Email["External email app"]
    Day --> Student
    Day -->|Back| RegisterClass
    Review --> Student
    Archived --> Student
    Dates -.->|Save / Cancel| Classes
    Fee -.->|Save / Back / Cancel| RegisterClass
    Term -.->|Save / Back / Cancel| RegisterClass
    ClassForm -.->|Save| RegisterClass
```

## 4. Materials, finance, projects and settings

```mermaid
flowchart LR
    Dashboard["Dashboard"]
    Materials["Materials<br/>/materials/"]
    MaterialForm["Add / edit / duplicate material<br/>/materials/add/ or /materials/ID/edit/"]
    Arrange["Arrange materials and categories<br/>/materials/arrange/"]
    Silver["Choose silver materials<br/>/materials/silver/"]
    History["Material and silver price history<br/>/materials/history/"]
    Grid["Edit section: inline grid, not a separate full page"]
    Check["Check supplier prices: inline results and confirmation"]
    Suppliers["External supplier websites"]
    Reports["Reports<br/>/reports/"]
    Downloads["CSV downloads: monthly, payments, purchases"]
    Payments["Payments<br/>/payments/"]
    PaymentForm["Record payment"]
    PaymentEdit["Edit payment"]
    Sales["Sales<br/>/sales/"]
    SaleForm["Record / edit sale<br/>/sales/new/ or /sales/ID/edit/"]
    Projects["Projects<br/>/projects/"]
    ProjectForm["Add / edit project<br/>/projects/add/ or /projects/ID/edit/"]
    Student["Student details"]
    Balances["Balances to chase"]
    Purchase["Choose student for purchase"]
    RegisterClass["Selected class register"]
    StudentForm["Add student"]
    Settings["Settings"]
    Admin["Django admin"]
    Dates["Set term dates"]

    Dashboard --> Materials
    Dashboard --> Sales
    Dashboard --> Balances
    Dashboard --> Purchase
    Dashboard --> PaymentForm
    Dashboard --> SaleForm
    Dashboard --> RegisterClass
    Dashboard --> StudentForm
    Dashboard -->|Sales channel| Student
    Materials --> MaterialForm
    Materials --> Arrange
    Materials --> Silver
    Materials --> History
    Materials -.->|Edit section| Grid
    Grid -.->|Save / Cancel| Materials
    Materials -.->|Check supplier prices| Check
    Check -.->|Apply prices| Materials
    Check -->|Edit link| MaterialForm
    Materials -.->|Supplier link| Suppliers
    MaterialForm -.->|Save / Cancel| Materials
    MaterialForm -->|Duplicate| MaterialForm
    History -->|Edit selected material| MaterialForm
    History --> Materials
    History -.-> SilverEntry["Inline add / delete silver price"]
    Reports --> Sales
    Reports --> History
    Reports --> Dates
    Reports -.-> Downloads
    Payments --> PaymentForm
    Payments --> PaymentEdit
    Payments --> Student
    Payments --> SaleForm
    Payments --> Sales
    Sales --> SaleForm
    Sales -->|Linked student| Student
    Projects --> ProjectForm
    Projects -->|Participating student| Student
    ProjectForm -.->|Save / Cancel| Projects
    Settings --> Admin
```

## Background work and non-page actions

These are intentionally not drawn as ordinary pages:

- **Daily online-price refresh:** the first signed-in app visit starts a
  background update; the shared banner polls an HTML status fragment. Its
  Materials link returns to the materials page.
- **Daily silver-rate check** and **daily backup:** background/server work.
- **HTMX fragments:** student balance, material search, price previews, supplier
  fetch results, grid price cells, candidate students and filtered table rows.
- **POST actions:** delete, archive/restore, reorder, Quick add toggle, deliberate
  low-markup acknowledgement, adding students to a class, price application,
  payments, and Undo. They update data and/or return to a page.
- The legacy `settle_up` endpoint still exists, but neither current cash nor card
  button uses it. Both now open the normal payment form.
- Django admin is represented as one destination; its generated model screens
  are not expanded here.

## Source of truth

- [App routes](tracker/urls.py)
- [Login and admin routes](studio/urls.py)
- [Shared menu](tracker/templates/base.html)
- [Page templates](tracker/templates/tracker/)
- [Views and return navigation](tracker/views.py)

This is a manually maintained navigation map, not a generated route listing.
Update it when adding pages or changing their links.
