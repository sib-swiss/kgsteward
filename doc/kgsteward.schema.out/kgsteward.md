# Untitled object in undefined Schema

```txt
https://example.com/schema.json
```

This is the JSON schema to validate YAML files for kgstweard

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                      |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :------------------------------------------------------------------------------ |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Allowed               | none                | [kgsteward.schema.json](../../out/kgsteward.schema.json "open original schema") |

## Untitled object in undefined Type

`object` ([Details](kgsteward.md))

# Untitled object in undefined Properties

| Property                   | Type     | Required | Nullable       | Defined by                                                                                                     |
| :------------------------- | :------- | :------- | :------------- | :------------------------------------------------------------------------------------------------------------- |
| [server\_url](#server_url) | `string` | Required | cannot be null | [Untitled schema](kgsteward-properties-server_url.md "https://example.com/schema.json#/properties/server_url") |
| [graphs](#graphs)          | `array`  | Required | cannot be null | [Untitled schema](kgsteward-properties-graphs.md "https://example.com/schema.json#/properties/graphs")         |
| Additional Properties      | Any      | Optional | can be null    |                                                                                                                |

## server\_url

The server URL. This key is stored in the execution environment and can be accessed through  `${server_url}`. `endpoint` is a deprecated synonym for `server_url` which is misleading as the real SPARQL endpoint location depend on the store.

`server_url`

* is required

* Type: `string` ([server\_url](kgsteward-properties-server_url.md))

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-server_url.md "https://example.com/schema.json#/properties/server_url")

### server\_url Type

`string` ([server\_url](kgsteward-properties-server_url.md))

### server\_url Constraints

**pattern**: the string must match the following regular expression:&#x20;

```regexp
^https?://
```

[try pattern](https://regexr.com/?expression=%5Ehttps%3F%3A%2F%2F "try regular expression with regexr.com")

**URI**: the string must be a URI, according to [RFC 3986](https://tools.ietf.org/html/rfc3986 "check the specification")

### server\_url Default Value

The default value is:

```json
"http://localhost:7200"
```

## graphs



`graphs`

* is required

* Type: `object[]` ([Details](kgsteward-properties-graphs-items.md))

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-graphs.md "https://example.com/schema.json#/properties/graphs")

### graphs Type

`object[]` ([Details](kgsteward-properties-graphs-items.md))

### graphs Constraints

**minimum number of items**: the minimum number of items for this array is: `1`

**unique items**: all items in this array must be unique. Duplicates are not allowed.

## Additional Properties

Additional properties are allowed and do not have to follow a specific schema
