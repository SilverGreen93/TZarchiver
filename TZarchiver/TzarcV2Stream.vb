Imports System.IO
Imports System.IO.Compression

''' <summary>
''' Read-only stream that decompresses the payload of a TZarc version 2 archive.
''' The base stream must be positioned right after the 8-byte "TZac" + version header.
''' The decompressed data has the same layout as a version 1 archive starting at the file count field.
''' </summary>
Public Class TzarcV2Stream
    Inherits Stream

    Private ReadOnly baseStream As Stream
    Private ReadOnly blockSizes As Integer()
    Private ReadOnly totalLength As Long
    Private nextBlock As Integer = 0
    Private blockData As Byte() = New Byte() {}
    Private blockPos As Integer = 0
    Private position_ As Long = 0

    Public Sub New(source As Stream)
        baseStream = source
        Dim reader As New BinaryReader(source) 'little endian; not disposed so the base stream stays open
        totalLength = reader.ReadInt64()
        Dim blockCount As Integer = reader.ReadInt32()
        If totalLength < 0 OrElse blockCount < 0 Then Throw New InvalidDataException("Invalid TZarc v2 header")
        ReDim blockSizes(blockCount - 1)
        For i As Integer = 0 To blockCount - 1
            blockSizes(i) = CInt(reader.ReadUInt16()) + 1 'stored as compressed size - 1
        Next
    End Sub

    'each block is a separate zlib stream (2-byte header, raw deflate data, 4-byte Adler-32)
    Private Function LoadNextBlock() As Boolean
        If nextBlock >= blockSizes.Length Then Return False
        Dim compSize As Integer = blockSizes(nextBlock)
        Dim comp(compSize - 1) As Byte
        Dim got As Integer = 0
        While got < compSize
            Dim n As Integer = baseStream.Read(comp, got, compSize - got)
            If n = 0 Then Throw New EndOfStreamException("Unexpected end of TZarc v2 data in block " & nextBlock)
            got += n
        End While

        If compSize < 6 OrElse (comp(0) And &HF) <> 8 OrElse ((CInt(comp(0)) << 8) Or comp(1)) Mod 31 <> 0 Then
            Throw New InvalidDataException("Invalid zlib header in TZarc v2 block " & nextBlock)
        End If

        Using deflate As New DeflateStream(New MemoryStream(comp, 2, compSize - 2), CompressionMode.Decompress),
              output As New MemoryStream()
            deflate.CopyTo(output)
            blockData = output.ToArray()
        End Using
        blockPos = 0
        nextBlock += 1
        Return True
    End Function

    Public Overrides Function Read(buffer() As Byte, offset As Integer, count As Integer) As Integer
        Dim total As Integer = 0
        While count > 0
            If blockPos >= blockData.Length Then
                If Not LoadNextBlock() Then Exit While
                Continue While
            End If
            Dim n As Integer = Math.Min(count, blockData.Length - blockPos)
            System.Buffer.BlockCopy(blockData, blockPos, buffer, offset, n)
            blockPos += n
            offset += n
            count -= n
            total += n
        End While
        position_ += total
        Return total
    End Function

    Public Overrides ReadOnly Property CanRead As Boolean
        Get
            Return True
        End Get
    End Property

    Public Overrides ReadOnly Property CanSeek As Boolean
        Get
            Return False
        End Get
    End Property

    Public Overrides ReadOnly Property CanWrite As Boolean
        Get
            Return False
        End Get
    End Property

    Public Overrides ReadOnly Property Length As Long
        Get
            Return totalLength
        End Get
    End Property

    Public Overrides Property Position As Long
        Get
            Return position_
        End Get
        Set(value As Long)
            Throw New NotSupportedException()
        End Set
    End Property

    Public Overrides Sub Flush()
    End Sub

    Public Overrides Function Seek(offset As Long, origin As SeekOrigin) As Long
        Throw New NotSupportedException()
    End Function

    Public Overrides Sub SetLength(value As Long)
        Throw New NotSupportedException()
    End Sub

    Public Overrides Sub Write(buffer() As Byte, offset As Integer, count As Integer)
        Throw New NotSupportedException()
    End Sub

    Protected Overrides Sub Dispose(disposing As Boolean)
        If disposing Then baseStream.Dispose()
        MyBase.Dispose(disposing)
    End Sub
End Class
