export const solutions = [
  {
    id: "cultivation",
    name: "Cultivation",
    short: "From room to harvest.",
    title: "Keep the growing operation in view.",
    description:
      "Explore plant records, room context and growth phases without making the grow team think like a retail buyer.",
    points: [
      "Plant and room context",
      "Growth phase tracking",
      "Estimated harvest dates and plant history",
    ],
    question:
      "Bring your room structure, plant workflows and harvest handoffs to the beta conversation.",
  },
  {
    id: "production",
    name: "Production / Manufacturing",
    short: "From bulk to finished goods.",
    title: "Know where the run stands.",
    description:
      "Explore production and extraction workspaces with inputs, outputs, yields and packaging context close to the work.",
    points: [
      "Production and extraction runs",
      "Materials, yields and costing",
      "Packaging, labels and QA review",
    ],
    question:
      "Walk through one real production process, from source material to finished goods.",
  },
  {
    id: "retail",
    name: "Retail Operations",
    short: "From receiving to the next buy.",
    title: "Give the next buying decision some context.",
    description:
      "Explore buying, receiving and inventory workspaces built around sellable stock and the decisions a store makes every day.",
    points: [
      "Purchasing and receiving",
      "Inventory counts and product records",
      "Sales intelligence and reorder review",
    ],
    question:
      "Tell us about your POS, inventory exports and the buying decisions that take too long.",
  },
  {
    id: "vertical",
    name: "Vertically Integrated",
    short: "See across the handoffs.",
    title: "Different licenses. A shared operational picture.",
    description:
      "Evaluate cultivation, manufacturing and retail together, while keeping facility and license context visible.",
    points: [
      "Operation-specific workspaces",
      "Facility and license context",
      "Material and commercial handoffs",
    ],
    question:
      "Map one cross-facility journey with us. Confirm each handoff before expanding your beta scope.",
  },
] as const;

export const marketingFaqs = [
  {
    question: "What is DoobieLogic?",
    answer:
      "DoobieLogic is cannabis operations and ERP software in beta. It brings buying, inventory, receiving, production, extraction and operational intelligence into a shared platform. Access and workflow scope are agreed with approved beta partners.",
  },
  {
    question: "Which operations is it built for?",
    answer:
      "Cultivation, production and manufacturing, retail, and vertically integrated cannabis operations. Beta workspaces address plants and rooms, production runs and materials, or buying and sellable inventory according to the operation. We review fit for your workflows before onboarding.",
  },
  {
    question: "Can we evaluate multiple facilities?",
    answer:
      "The platform includes facility and license context and role-based access controls. Multi-facility and vertically integrated operators can apply for beta access; the team will review the facilities, permissions and handoffs to include in testing.",
  },
  {
    question: "Does DoobieLogic integrate with Metrc?",
    answer:
      "Metrc integration is in validation. DoobieLogic includes Metrc-aware workflows, but this is not a claim of certification, production readiness or support in every state. State, license and provider access need to be confirmed for your beta scope.",
  },
  {
    question: "Will it replace our POS or accounting system?",
    answer:
      "Do not assume a replacement or a live connection. Bring your current systems and required data flows to the beta review. Available imports and integrations must be validated for your operation before you rely on them.",
  },
  {
    question: "What does Doobie Agent do?",
    answer:
      "Doobie Agent is a beta assistant for questions, explanations and recommendations using available operational context. AI runtime tools are read-only; governed actions use separate controls. Your team remains responsible for operational decisions and regulated work.",
  },
  {
    question: "How do we get access, and what happens next?",
    answer:
      "Apply through the Beta Partner Program. Tell us your operation type, state, facilities, current systems and biggest operational problem. The team reviews fit for the current phase; approved partners receive onboarding access and take part in agreed testing and feedback.",
  },
] as const;
