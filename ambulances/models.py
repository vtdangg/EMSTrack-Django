from enum import Enum
from django.utils import timezone

from django.db import models

from django.contrib.gis.db import models
from django.contrib.gis.geos import LineString, Point

Tijuana = Point(-117.0382, 32.5149, srid=4326)
DefaultRoute = LineString((0, 0), (1, 1), srid=4326)

from django.contrib.auth.models import User

import .mqtt.publish as mqtt

# lazy client property
client = None
def get_client():

    if not client:
        client = mqtt.get_client()
    return client

# User and ambulance location models

# Ambulance model

class AmbulanceStatus(Enum):
    UK = 'Unknown'
    AV = 'Available'
    OS = 'Out of service'
    PB = 'Patient bound'
    AP = 'At patient'
    HB = 'Hospital bound'
    AH = 'At hospital'
    
class AmbulanceCapability(Enum):
    B = 'Basic'
    A = 'Advanced'
    R = 'Rescue'
    
class Ambulance(models.Model):

    # ambulance properties
    identifier = models.CharField(max_length=50, unique=True)

    AMBULANCE_CAPABILITY_CHOICES = \
        [(m.name, m.value) for m in AmbulanceCapability]
    capability = models.CharField(max_length=1,
                                  choices = AMBULANCE_CAPABILITY_CHOICES)
    
    # comment
    comment = models.CharField(max_length=254, default="")

    # status
    AMBULANCE_STATUS_CHOICES = \
        [(m.name, m.value) for m in AmbulanceStatus]
    status = models.CharField(max_length=2,
                              choices=AMBULANCE_STATUS_CHOICES,
                              default=AmbulanceStatus.UK.name)
    
    # location
    orientation = models.FloatField(null=True, blank=True)
    location = models.PointField(srid=4326, null=True, blank=True)
    location_timestamp = models.DateTimeField(null=True, blank=True)
    
    updated_by = models.ForeignKey(User,
                                   on_delete=models.CASCADE)
    updated_on = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        get_client().publish_ambulance(self, **kwargs)

    def delete(self, *args, **kwargs):
        get_client().remove_ambulance(self)
        super().delete(*args, **kwargs) 
    
    def __str__(self):
        return ('> Ambulance {}(id={}) ({}) [{}]:\n' +
                '    Status: {}\n' +
                '  Location: {} @ {}\n' +
                '   Updated: {} by {}').format(self.identifier,
                                               self.id,
                                               AmbulanceCapability[self.capability].value,
                                               self.comment,
                                               AmbulanceStatus[self.status].value,
                                               self.location,
                                               self.location_timestamp,
                                               self.updated_by,
                                               self.updated_on)

class AmbulanceRoute(models.Model):

    ambulance = models.ForeignKey(Ambulance,
                                  on_delete=models.CASCADE)
    active = models.BooleanField(default=False)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    #points = models.ManyToManyField(AmbulanceUpdate)
    
class AmbulancePermission(models.Model):

    ambulance = models.ForeignKey(Ambulance,
                                  on_delete=models.CASCADE)
    can_read = models.BooleanField(default=True)
    can_write = models.BooleanField(default=False)

    def __str__(self):
        return  '{}(id={}): read[{}] write[{}]'.format(self.ambulance.identifier,
                                                       self.ambulance.id,
                                                       self.can_read,
                                                       self.can_write)
    
# Hospital model

class Hospital(models.Model):
    
    name = models.CharField(max_length=254, unique=True)
    address = models.CharField(max_length=254, default="")
    location = models.PointField(srid=4326, null=True, blank=True)
    
    # comment
    comment = models.CharField(max_length=254, default="")
    
    updated_by = models.ForeignKey(User,
                                   on_delete=models.CASCADE)
    updated_on = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs) 
        get_client().publish_hospital(self, **kwargs)

    def delete(self, *args, **kwargs):
        get_client().remove_hospital(self)
        super().delete(*args, **kwargs)
        
    def __str__(self):
        return ('> Hospital {}(id={})\n' +
                '   Address: {}\n' +
                '  Location: {}\n' +
                '   Updated: {} by {}').format(self.name,
                                               self.id,
                                               self.address,
                                               self.location,
                                               self.updated_by,
                                               self.updated_on)

class HospitalPermission(models.Model):

    hospital = models.ForeignKey(Hospital,
                                  on_delete=models.CASCADE)
    can_read = models.BooleanField(default=True)
    can_write = models.BooleanField(default=False)

    def __str__(self):
        return  '{}(id={}): read[{}] write[{}]'.format(self.hospital.name,
                                                       self.hospital.id,
                                                       self.can_read,
                                                       self.can_write)

class EquipmentType(Enum):
    B = 'Boolean'
    I = 'Integer'
    S = 'String'
    
class Equipment(models.Model):

    name = models.CharField(max_length=254, unique=True)

    EQUIPMENT_ETYPE_CHOICES = \
        [(m.name, m.value) for m in EquipmentType]
    etype = models.CharField(max_length=1,
                             choices = EQUIPMENT_ETYPE_CHOICES)
    
    toggleable = models.BooleanField(default=False)

    def __str__(self):
        return "{}: {} ({})".format(self.id, self.name, self.toggleable)


class HospitalEquipment(models.Model):

    hospital = models.ForeignKey(Hospital,
                                 on_delete=models.CASCADE)
    equipment = models.ForeignKey(Equipment,
                                  on_delete=models.CASCADE)

    value = models.CharField(max_length=254)
    comment = models.CharField(max_length=254)
    
    quantity = models.IntegerField(default=0)
    
    updated_by = models.ForeignKey(User,
                                   on_delete=models.CASCADE)
    updated_on = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        created = self.pk is None
        super().save(*args, **kwargs) 
        get_client().publish_hospital_equipment(self)
        if created:
            get_client().publish_hospital_metadata(self.hospital)

    def delete(self, *args, **kwargs):
        get_client().remove_hospital_equipment(self)
        get_client().publish_hospital_metadata(self.hospital)
        super().delete(*args, **kwargs)
        
    class Meta:
        unique_together = ('hospital', 'equipment',)

    def __str__(self):
        return "Hospital: {}, Equipment: {}, Count: {}".format(self.hospital, self.equipment, self.quantity)

    
# Profile and state

class Profile(models.Model):

    user = models.OneToOneField(User,
                                on_delete=models.CASCADE)
    ambulances = models.ManyToManyField(AmbulancePermission)
    hospitals = models.ManyToManyField(HospitalPermission)

    def __str__(self):
        return ('> Ambulances:\n' +
                '\n'.join('  {}'.format(k) for k in self.ambulances.all()) +
                '\n> Hospitals:\n' +
                '\n'.join('  {}'.format(k) for k in self.hospitals.all()))
    
class State(models.Model):

    user = models.OneToOneField(User,
                                on_delete=models.CASCADE)
    hospital = models.ForeignKey(Hospital,
                                 on_delete=models.CASCADE,
                                 null=True, blank=True)
    ambulance = models.ForeignKey(Ambulance,
                                  on_delete=models.CASCADE,
                                  null=True, blank=True)

# THESE NEED REVISING
    
class Call(models.Model):

    #call metadata (status not required for now)
    active = models.BooleanField(default=False)
    status = models.CharField(max_length=254, default= "", blank=True)
    # ambulance assigned to Call (Foreign Key)
    ambulance = models.ForeignKey(Ambulance, on_delete=models.CASCADE, default=1)
    name = models.CharField(max_length=254, default = "")
    # address-related info
    residential_unit = models.CharField(max_length=254, default = "None")
    stmain_number = models.CharField(max_length=254, default = "None")
    delegation = models.CharField(max_length=254, default = "None")
    zipcode = models.CharField(max_length=254, default = "22500")
    city = models.CharField(max_length=254, default="Tijuana")
    state = models.CharField(max_length=254, default="Baja California")
    location = models.PointField(srid=4326, default=Tijuana)
    # assignment = base name and #
    assignment = models.CharField(max_length=254, default = "None")
    # short description of the patient's injury
    description = models.CharField(max_length=500, default = "None")
    # response time related info
    call_time = models.DateTimeField(default = timezone.now)
    departure_time = models.DateTimeField(blank = True, null = True)
    transfer_time = models.DateTimeField(blank = True, null = True)
    hospital_time = models.DateTimeField(blank = True, null = True)
    base_time = models.DateTimeField(blank = True, null = True)
    PRIORITIES = [('A','A'),('B','B'),('C','C'),('D','D'),('E','E')]
    priority = models.CharField(max_length=254, choices=PRIORITIES, default='A')

    def __str__(self):
        return "({}): {}, {}".format(self.priority, self.residential_unit, self.stmain_number)


class Region(models.Model):
    name = models.CharField(max_length=254, unique=True)
    center = models.PointField(srid=4326, null=True)

    def __str__(self):
        return self.name


class Base(models.Model):
    name = models.CharField(max_length=254, unique=True)
    location = models.PointField(srid=4326, null=True)

    def __str__(self):
        return self.name
