# Untitled string in undefined Schema

```txt
https://example.com/schema.json#/properties/server_url
```

The server URL. This key is stored in the execution environment and can be accessed through  `${server_url}`. `endpoint` is a deprecated synonym for `server_url` which is misleading as the real SPARQL endpoint location depend on the store.

| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Allowed               | none                | [kgsteward.schema.json\*](../../out/kgsteward.schema.json "open original schema") |

## server\_url Type

`string`

## server\_url Constraints

**pattern**: the string must match the following regular expression:&#x20;

```regexp
^https?://
```

[try pattern](https://regexr.com/?expression=%5Ehttps%3F%3A%2F%2F "try regular expression with regexr.com")

**URI**: the string must be a URI, according to [RFC 3986](https://tools.ietf.org/html/rfc3986 "check the specification")

## server\_url Default Value

The default value is:

```json
"http://localhost:7200"
```
