from webob.exc import HTTPFound

import formish
import schemaish
from validatish import validator

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.util import class_mapper

from repoze.bfg.url import route_url
from repoze.bfg.chameleon_zpt import get_template

from seantisinvoice.models import DBSession
from seantisinvoice.models import CustomerContact, Invoice, InvoiceItem, Company

class InvoiceItemSchema(schemaish.Structure):
    
    item_id = schemaish.Integer()
    service_title = schemaish.String(validator=validator.Required())
    service_description = schemaish.String(validator=validator.Required())
    amount = schemaish.Float(description="Enter the amout")
    hours = schemaish.Float(description="Or hours (will be multiplied by your rate)")
    
invoice_item_schema = InvoiceItemSchema()

class InvoiceSchema(schemaish.Structure):
    
    customer_contact_id = schemaish.String(validator=validator.Required())
    project_description = schemaish.String(validator=validator.Required())
    date = schemaish.Date(validator=validator.Required())
    invoice_number = schemaish.Integer(validator=validator.Required())
    recurring_term = schemaish.Integer()
    payment_term = schemaish.Integer(validator=validator.Required())
    currency = schemaish.String(validator=validator.Required())
    tax = schemaish.Float()
    item_list = schemaish.Sequence(invoice_item_schema)
    
invoice_schema = InvoiceSchema()

class InvoiceController(object):
    
    def __init__(self, context, request):
        self.request = request
        
    def form_fields(self):
        return invoice_schema.attrs
        
    def form_defaults(self):
        
        defaults = {
            'currency' : 'CHF',
            'payment_term' : '30',
            'tax' : '7.6',
        }
        
        if "invoice" in self.request.matchdict:
            invoice_id = self.request.matchdict['invoice']
            try:
                session = DBSession()
                invoice = session.query(Invoice).filter_by(id=invoice_id).one()
            except NoResultFound:
                return HTTPFound(location = route_url('invoices', self.request))  
            field_names = [ p.key for p in class_mapper(Invoice).iterate_properties ]
            form_fields = [ field[0] for field in invoice_schema.attrs ]
            for field_name in field_names:
                if field_name in form_fields:
                    defaults[field_name] = getattr(invoice, field_name)
                    
            # Default values for the item subforms
            defaults['item_list'] = []
            for item in invoice.items:
                item_defaults = {}
                field_names = [ p.key for p in class_mapper(InvoiceItem).iterate_properties ]
                form_fields = [ field[0] for field in invoice_item_schema.attrs ]
                for field_name in field_names:
                    if field_name in form_fields:
                        item_defaults[field_name] = getattr(item, field_name)
                item_defaults['item_id'] = item.id
                defaults['item_list'].append(item_defaults)
        
        return defaults
        
    def form_widgets(self, fields):
        widgets = {}
        widgets['date'] = formish.DateParts(day_first=True)
        session = DBSession()
        options = []
        for contact in session.query(CustomerContact).all():
            options.append((contact.id, '%s: %s %s' % (contact.customer.name, contact.first_name, contact.last_name)))
        widgets['customer_contact_id'] = formish.SelectChoice(options=options)
        widgets['item_list'] = formish.SequenceDefault(min_start_fields=1)
        widgets['item_list.*.item_id'] = formish.Hidden()
        
        return widgets
        
    def __call__(self):
        main = get_template('templates/master.pt')
        return dict(request=self.request, main=main)
        
    def _apply_data(self, invoice, converted):
        # Apply schema fields to the customer object
        field_names = [ p.key for p in class_mapper(Invoice).iterate_properties ]
        for field_name in field_names:
            if field_name in converted.keys():
                setattr(invoice, field_name, converted[field_name])
                
        # Apply data of the items subforms
        session = DBSession()
        item_map = {}
        for item in invoice.items:
            item_map[item.id] = item
        for item_data in converted['item_list']:
            if item_data['item_id']:
                item_id = item_data['item_id']
                item = item_map[item_id]
                del item_map[item_id]
            else:
                item = InvoiceItem()
                item.invoice = invoice
                session.add(item)
            # Apply schema fields to the customer object
            field_names = [ p.key for p in class_mapper(InvoiceItem).iterate_properties ]
            for field_name in field_names:
                if field_name in item_data.keys():
                    setattr(item, field_name, item_data[field_name])
        # Remove contact items that have been removed in the form
        for item in item_map.values():
            session.delete(item)
        
    def handle_add(self, converted):
        session = DBSession()
        invoice = Invoice()
        invoice.company = session.query(Company).first()
        self._apply_data(invoice, converted)
        session.add(invoice)
        return HTTPFound(location=route_url('invoices', self.request))
        
    def handle_submit(self, converted):
        invoice_id = self.request.matchdict['invoice']
        session = DBSession()
        invoice = session.query(Invoice).filter_by(id=invoice_id).one()
        self._apply_data(invoice, converted)
        return HTTPFound(location=route_url('invoices', self.request))
        
    def handle_cancel(self):
        return HTTPFound(location=route_url('invoices', self.request))

def view_invoices(request):
    session = DBSession()
    invoices = session.query(Invoice).all()
    main = get_template('templates/master.pt')
    return dict(request=request, main=main, invoices=invoices)
    
def view_reports(request):
    session = DBSession()
    invoices = session.query(Invoice).filter(Invoice.recurring_term != None)    
    main = get_template('templates/master.pt')
    return dict(request=request, main=main, invoices=invoices)