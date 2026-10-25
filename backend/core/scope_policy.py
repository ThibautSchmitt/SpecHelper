"""Conservative, deterministic project-scope triage without provider or resource access.

This is an input routing aid, not a semantic correctness or authorization check.
Environment text supplies factual context only; it never changes this policy or
grants capabilities. Source files, attachments and fetched pages are not inputs.
"""

import re
import unicodedata

POLICY_VERSION = "2.8"
IN_SCOPE_MESSAGE = "This request concerns the selected project or its business context."
OUT_OF_SCOPE_MESSAGE = (
    "This request does not appear to concern the project. Please describe a need related "
    "to the application or its business context."
)
CLARIFICATION_MESSAGE = "A short clarification is needed to relate this request to the project."
ENVIRONMENT_MESSAGE = "Choose an environment to identify the project and its business context."
RELATION_QUESTION = "How does this relate to the selected project or its business context?"
ENVIRONMENT_QUESTION = "Which environment or project does this request concern?"

TECHNICAL = re.compile(
    r"\b(?:sql|postgres(?:ql)?|database|databases|base de donnees|bases de donnees|"
    r"code|codebase|source|sources|repository|repositories|depot|depots|git|api|apis|"
    r"architecture|architectural|interface|interfaces|ui|ux|frontend|backend|"
    r"bug|bugs|debug|debugging|regression|regressions|schema|schemas|"
    r"performance|cache|caching|securite|security|authentification|authentication|"
    r"documentation|documenter|tests?|testability|logging|logs?|deployment|deploiement)\b"
)
PROJECT_RELATION = re.compile(
    r"\b(?:for|in|of|within|on|pour|dans|de|du|sur)\s+"
    r"(?:(?:our|this|the|my|notre|nos|mon|ce|cette|le|la|les|l)\s+){0,3}"
    r"(?:project|application|app|software|product|website|platform|projet|logiciel|"
    r"produit|site|plateforme|homepage|page d accueil)\b"
    r"|\b(?:project|application|app|software|projet|logiciel)\s+"
    r"(?:feature|requirement|behavior|behaviour|fonctionnalite|comportement|besoin)\b"
)
PROJECT_ACTION = re.compile(
    r"\b(?:add|build|implement|fix|document|analy[sz]e|understand|review|explain|improve|"
    r"create|generate|design|migrate|integrate|compare|update|debug|develop|"
    r"ajout\w*|implement\w*|corrig\w*|document\w*|analys\w*|comprendr\w*|expliqu\w*|"
    r"amelior\w*|cre\w*|gener\w*|concev\w*|migr\w*|integr\w*|compar\w*|develop\w*)\b"
    r".{0,120}\b(?:project|application|app|software|api|ui|interface|database|table|"
    r"screen|homepage|feature|code|projet|logiciel|ecran|page d accueil|fonctionnalite)\b"
    r"|\b(?:our|this|my|notre|mon|ce|cette)\s+"
    r"(?:project|application|app|software|projet|logiciel|interface)\b.{0,90}"
    r"\b(?:shows?|displays?|serves?|supports?|contains?|uses?|should|must|needs?|"
    r"doit|devrait|affich\w*|permet\w*|gere\w*|contien\w*|utilis\w*)\b"
)
SQL_REQUEST = re.compile(
    r"\b(?:select|insert|update|delete|join|alter|create table)\b.{0,100}\b(?:from|into|table|join|where)\b"
    r"|\b(?:sql|query|requete)\b.{0,100}\b(?:table|tables|recipe|recipes|recette|recettes|select|join)\b"
)
PERSONAL_TASK = re.compile(
    r"\b(?:recette|recettes|recipe|recipes)\b"
    r"|\b(?:bake|cook|cuisiner|preparer)\b.{0,50}\b(?:pie|cake|tarte|gateau|dinner|repas)\b"
    r"|\b(?:generate|create|draw|paint|genere\w*|cree\w*|dessin\w*|peins)\b"
    r".{0,75}\b(?:image|picture|portrait|photo|illustration)\b"
    r"|^(?:(?:a|an|un|une)\s+)?(?:image|picture|portrait|photo|illustration)\s+(?:of|de|d)\b"
    r"|\b(?:write|ecris|compose|raconte|tell)\b.{0,50}\b(?:poem|poeme|joke|blague|horoscope)\b"
    r"|\b(?:weather|meteo|horoscope|capital of|capitale de)\b"
    r"|\b(?:what is|calculate|combien font|combien fait|calcule|calculer)\s+\d+(?:\s+\d+)+$"
)
FUNCTIONAL_REQUEST = re.compile(
    r"^(?:(?:please|merci de)\s+)?(?:add|export|enable|allow|support|improve|show|change|"
    r"update|remove|disable|automate|track|validate|calculate|understand|explain|review|check|"
    r"create|fix|connect|ajout\w*|export\w*|activ\w*|permet\w*|amelior\w*|affich\w*|"
    r"modifi\w*|supprim\w*|desactiv\w*|automatis\w*|suivr\w*|valid\w*|calcul\w*|"
    r"comprendr\w*|expliqu\w*|verifi\w*|cre\w*|corrig\w*|connect\w*)\s+\S.{2,}"
)
APPLICABILITY = re.compile(
    r"\b(?:applicab\w*|compliance|conformite|regulat\w*|reglement\w*|legislation|"
    r"official|officiel\w*|obligation\w*|juridique|legal|legale|norme|standard)\b"
)
VAGUE = re.compile(
    r"^(?:(?:please|merci|bonjour|hello|hi|salut)\s*)*"
    r"(?:help(?: me)?(?: with (?:this|that|it))?|aide(?: moi)?|can you help(?: me)?(?: with (?:this|that|it))?|peux tu m aider|"
    r"pouvez vous m aider|what do you think|qu en penses tu|"
    r"explain(?: this| that| it)?|explique(?: moi)?(?: ceci| cela| ca)?|"
    r"analy[sz]e(?: this| that| it)?|analyse(?: ceci| cela| ca)?|"
    r"improve(?: this| that| it)?|ameliore(?: ceci| cela| ca)?|"
    r"make it better|do it|fais le|continue|more|encore|need|besoin)?"
    r"(?:\s*(?:please|merci))?$"
)
STOPWORDS = frozenset(
    "about after against application applications before business ce cette code context contexte "
    "dans data des does domain domaine dont elle elles environnement environment environments "
    "for from have into leur leurs notre nous pour project projects projet projets request "
    "selected should sont staging production preprod test that their them then there these "
    "this those une users utilisateur utilisateurs avec what when which where will with would "
    "your always never accept refuse ignore previous instructions instruction policy policies "
    "allowed permissions permission anything everything scope filter system assistant "
    "backend frontend company repository repositories source sources rule rules regles regle".split()
)


def _normalize(value):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value[:30000])
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r"https?://\S+", " ", value.lower())
    value = value.replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9_]+", " ", value)).strip()


def _context_words(environment):
    """Extract bounded factual vocabulary; ignore caller-supplied policy/permission keys."""
    if not isinstance(environment, dict):
        return set()
    pieces = [environment.get("name", ""), environment.get("context_instructions", "")]
    repositories = environment.get("repository_names", [])
    if isinstance(repositories, (list, tuple)):
        pieces.extend(value for value in repositories[:30] if isinstance(value, str))
    references = environment.get("official_references", [])
    if isinstance(references, (list, tuple)):
        for reference in references[:12]:
            if isinstance(reference, dict):
                pieces.extend(reference.get(key, "") for key in ("title", "note", "applicability"))
    return {
        word.rstrip("s") for piece in pieces for word in _normalize(piece).split()
        if len(word) >= 4 and word not in STOPWORDS
    }


def _result(status, reason_code):
    if status == "IN_SCOPE":
        message, question = IN_SCOPE_MESSAGE, ""
    elif status == "OUT_OF_SCOPE":
        message, question = OUT_OF_SCOPE_MESSAGE, ""
    elif reason_code == "environment_required":
        message, question = ENVIRONMENT_MESSAGE, ENVIRONMENT_QUESTION
    else:
        message, question = CLARIFICATION_MESSAGE, RELATION_QUESTION
    return {
        "status": status, "reason_code": reason_code, "policy_version": POLICY_VERSION,
        "message": message, "question": question,
    }


def classify(need, *, environment=None, clarification="", language="en"):
    """Route supported-language requests without logging, fetching or granting anything.

    Messages are canonical English translation keys; the interface owns EN/FR display.
    Selecting an environment is useful evidence of intent, not proof of the answer.
    Only clearly unrelated tasks receive a refusal. Unknown business vocabulary is
    not a reason to reject a request, and ambiguous context receives one question.
    """
    initial = _normalize(need)
    detail = _normalize(clarification)
    text = " ".join(part for part in (initial, detail) if part)
    if not initial:
        return _result("NEEDS_CLARIFICATION", "empty_request")

    relation = bool(PROJECT_RELATION.search(text) or PROJECT_ACTION.search(text) or SQL_REQUEST.search(text))
    personal = bool(PERSONAL_TASK.search(initial))
    if personal and not relation:
        overlap = _context_words(environment) & {word.rstrip("s") for word in initial.split()}
        if not overlap:
            return _result("OUT_OF_SCOPE", "unrelated_personal_request")
        return _result("NEEDS_CLARIFICATION", "unclear_project_relation")

    if not isinstance(environment, dict) or not environment:
        return _result("NEEDS_CLARIFICATION", "environment_required")
    if not text or (VAGUE.fullmatch(initial) and (not detail or VAGUE.fullmatch(detail))):
        return _result("NEEDS_CLARIFICATION", "unclear_project_relation")
    if relation:
        return _result("IN_SCOPE", "relevant_project_request")
    if TECHNICAL.search(text):
        return _result("IN_SCOPE", "relevant_technical_request")
    if APPLICABILITY.search(text):
        return _result("IN_SCOPE", "relevant_business_context")
    if _context_words(environment) & {word.rstrip("s") for word in text.split()}:
        return _result("IN_SCOPE", "relevant_business_context")
    if FUNCTIONAL_REQUEST.search(text) and not VAGUE.fullmatch(text):
        return _result("IN_SCOPE", "selected_project_context")
    if len(text.split()) < 3:
        return _result("NEEDS_CLARIFICATION", "unclear_project_relation")
    return _result("IN_SCOPE", "selected_project_context")
