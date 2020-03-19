import jsonobject


class BoundingBox(jsonobject.JsonObject):
    left = jsonobject.FloatProperty()
    top = jsonobject.FloatProperty()
    right = jsonobject.FloatProperty()
    bottom = jsonobject.FloatProperty()


class Prediction(jsonobject.JsonObject):
    label = jsonobject.StringProperty()
    confidence = jsonobject.FloatProperty()


class Face(jsonobject.JsonObject):
    top_prediction = jsonobject.ObjectProperty(Prediction)
    bounding_box = jsonobject.ObjectProperty(BoundingBox)
    all_predictions = jsonobject.ObjectProperty(Prediction)


class Response(jsonobject.JsonObject):
    faces = jsonobject.ListProperty(Face)