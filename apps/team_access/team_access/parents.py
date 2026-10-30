from crm.fcrm.doctype.crm_deal.crm_deal import CRMDeal
from crm.fcrm.doctype.crm_lead.crm_lead import CRMLead


class ActivityLead(CRMLead):
    no_feed_on_delete = True


class ActivityDeal(CRMDeal):
    no_feed_on_delete = True
